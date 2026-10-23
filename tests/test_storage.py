import json
from types import ModuleType
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from scripts.gerar_dados import FIELDS
from scripts.storage_io import StorageError, archive_source, archive_sources, publish_json, typed_row


def sample_row():
    return dict.fromkeys(FIELDS, "") | {
        "uf": "AL", "municipio": "Cidade", "cd_ibge": 2701506, "zona": 20,
        "secao": 1, "eleitores": 400, "lat_2t": -9.95,
        "regiao_longe_da_urna": None,
    }


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.upload = Mock()
        self.blob = Mock(upload_from_string=self.upload)
        self.blob.exists = Mock(return_value=False)
        self.blob.generation = 1
        self.bucket = Mock(blob=Mock(return_value=self.blob))
        self.client = Mock(bucket=Mock(return_value=self.bucket))
        storage = ModuleType("google.cloud.storage")
        storage.Client = Mock(return_value=self.client)
        exceptions = ModuleType("google.api_core.exceptions")

        class GoogleAPIError(Exception):
            pass

        class PreconditionFailed(GoogleAPIError):
            pass

        exceptions.GoogleAPIError = GoogleAPIError
        exceptions.PreconditionFailed = PreconditionFailed
        api_core = ModuleType("google.api_core")
        api_core.exceptions = exceptions
        auth_exceptions = ModuleType("google.auth.exceptions")

        class GoogleAuthError(Exception):
            pass

        auth_exceptions.GoogleAuthError = GoogleAuthError
        auth = ModuleType("google.auth")
        auth.exceptions = auth_exceptions
        cloud = ModuleType("google.cloud")
        cloud.storage = storage
        google = ModuleType("google")
        google.__path__ = []
        google.cloud = cloud
        google.api_core = api_core
        google.auth = auth
        self.google_modules = {
            "google": google,
            "google.cloud": cloud,
            "google.cloud.storage": storage,
            "google.api_core": api_core,
            "google.api_core.exceptions": exceptions,
            "google.auth": auth,
            "google.auth.exceptions": auth_exceptions,
        }

    def test_uploads_typed_json_snapshot(self):
        extracted_at = datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)
        versions = {"registry": {"source": "https://tse/registry.zip", "etag": '"abc"', "sha256": "0" * 64}}
        with patch.dict("sys.modules", self.google_modules):
            result = publish_json([sample_row()], FIELDS, {
                "bucket": "test-bucket", "object": "dash/snapshot.json",
            }, extracted_at, versions)
        self.assertEqual(result, "test-bucket/dash/snapshot.json")
        self.bucket.blob.assert_called_once_with("dash/snapshot.json")
        args, kwargs = self.upload.call_args
        payload = json.loads(args[0])
        snapshot = payload["snapshots"][0]
        self.assertEqual(snapshot["extracted_at"], extracted_at.isoformat())
        self.assertEqual(snapshot["sources"], versions)
        self.assertEqual(snapshot["rows"][0]["eleitores"], 400)
        self.assertIsNone(snapshot["rows"][0]["lat_1t"])
        self.assertIsNone(snapshot["rows"][0]["regiao_longe_da_urna"])
        self.assertNotIn("entrou_desde_15_10", snapshot["rows"][0])
        self.assertEqual(kwargs["content_type"], "application/json; charset=utf-8")
        self.assertEqual(kwargs["if_generation_match"], 0)
        self.assertEqual(self.blob.cache_control, "public, max-age=60")

    def test_rejects_empty_or_invalid_target_before_upload(self):
        extracted_at = datetime.now(timezone.utc)
        with self.assertRaisesRegex(StorageError, "vazia"):
            publish_json([], FIELDS, {"bucket": "test-bucket"}, extracted_at)
        with self.assertRaisesRegex(StorageError, "bucket"):
            publish_json([sample_row()], FIELDS, {"bucket": "INVALID"}, extracted_at)

    def test_rejects_invalid_numeric_and_boolean_values(self):
        row = sample_row() | {"eleitores": "1.5"}
        with self.assertRaisesRegex(StorageError, "Inteiro inválido"):
            typed_row(row, FIELDS)
        row = sample_row() | {"regiao_longe_da_urna": "unknown"}
        with self.assertRaisesRegex(StorageError, "Booleano inválido"):
            typed_row(row, FIELDS)

    def test_appends_each_extraction_and_preserves_legacy_snapshot(self):
        old_time = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
        new_time = datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc)
        self.blob.exists.return_value = True
        self.blob.updated = old_time
        self.blob.generation = 12
        self.blob.download_as_text.return_value = json.dumps({
            "rows":[sample_row() | {"entrou_desde_15_10":True}],
        })
        with patch.dict("sys.modules", self.google_modules):
            publish_json([sample_row() | {"secao":2}], FIELDS, {
                "bucket":"test-bucket",
            }, new_time)
        payload = json.loads(self.upload.call_args.args[0])
        self.assertEqual([item["extracted_at"] for item in payload["snapshots"]], [
            old_time.isoformat(), new_time.isoformat(),
        ])
        self.assertNotIn("entrou_desde_15_10", payload["snapshots"][0]["rows"][0])
        self.assertEqual(payload["snapshots"][1]["rows"][0]["secao"], 2)
        self.assertEqual(self.upload.call_args.kwargs["if_generation_match"],12)

    def test_appends_to_existing_snapshot_history(self):
        old_time = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
        current_time = datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc)
        self.blob.exists.return_value = True
        self.blob.generation = 21
        self.blob.download_as_text.return_value = json.dumps({
            "snapshots":[{
                "extracted_at":old_time.isoformat(),
                "rows":[typed_row(sample_row(), FIELDS)],
            }],
        })
        with patch.dict("sys.modules", self.google_modules):
            publish_json([sample_row()], FIELDS, {"bucket":"test-bucket"}, current_time)
        payload = json.loads(self.upload.call_args.args[0])
        self.assertEqual([snapshot["extracted_at"] for snapshot in payload["snapshots"]], [
            old_time.isoformat(), current_time.isoformat(),
        ])
        self.assertNotIn("sources", payload["snapshots"][1])

    def test_rejects_naive_extraction_timestamp(self):
        with self.assertRaisesRegex(StorageError, "fuso horário"):
            publish_json([sample_row()], FIELDS, {"bucket":"test-bucket"}, datetime(2026, 10, 19))

    def test_retries_concurrent_publication_and_merges_latest_history(self):
        from_time = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
        concurrent_time = datetime(2026, 10, 19, 13, tzinfo=timezone.utc)
        current_time = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
        first = {"extracted_at": from_time.isoformat(), "rows": [typed_row(sample_row(), FIELDS)]}
        concurrent = {"extracted_at": concurrent_time.isoformat(), "rows": [typed_row(sample_row(), FIELDS)]}
        self.blob.exists.return_value = True
        self.blob.download_as_text.side_effect = [
            json.dumps({"snapshots": [first]}),
            json.dumps({"snapshots": [first, concurrent]}),
        ]
        with patch.dict("sys.modules", self.google_modules):
            from google.api_core.exceptions import PreconditionFailed
            def upload(*args, **kwargs):
                if self.upload.call_count == 1:
                    self.blob.generation = 2
                    raise PreconditionFailed("generation changed")
            self.upload.side_effect = upload
            publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, current_time)
        snapshots = json.loads(self.upload.call_args.args[0])["snapshots"]
        self.assertEqual([s["extracted_at"] for s in snapshots], [
            from_time.isoformat(), concurrent_time.isoformat(), current_time.isoformat(),
        ])
        self.assertEqual(self.upload.call_args.kwargs["if_generation_match"], 2)
        self.assertEqual(self.blob.download_as_text.call_args_list[0].kwargs["if_generation_match"], 1)
        self.assertEqual(self.blob.download_as_text.call_args_list[1].kwargs["if_generation_match"], 2)

    def test_rejects_conflicting_timestamp_without_replacing_history(self):
        current_time = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
        self.blob.exists.return_value = True
        self.blob.download_as_text.return_value = json.dumps({"snapshots": [{
            "extracted_at": current_time.isoformat(),
            "rows": [typed_row(sample_row() | {"eleitores": 399}, FIELDS)],
        }]})
        with patch.dict("sys.modules", self.google_modules):
            with self.assertRaisesRegex(StorageError, "mesmo instante"):
                publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, current_time)
        self.upload.assert_not_called()

    def test_identical_publication_is_idempotent(self):
        current_time = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
        self.blob.exists.return_value = True
        self.blob.download_as_text.return_value = json.dumps({"snapshots": [{
            "extracted_at": current_time.isoformat(), "rows": [typed_row(sample_row(), FIELDS)],
        }]})
        with patch.dict("sys.modules", self.google_modules):
            publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, current_time)
        self.upload.assert_not_called()

    def test_preserves_historical_fields_and_sorts_timestamps_chronologically(self):
        old = {"extracted_at": "2026-10-19T14:00:00+00:00",
               "rows": [{"historical_field": "must survive"}], "sources": {"sha256": "old"}}
        self.blob.exists.return_value = True
        self.blob.download_as_text.return_value = json.dumps({"snapshots": [old]})
        with patch.dict("sys.modules", self.google_modules):
            publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"},
                         datetime(2026, 10, 19, 14, 0, 0, 1, tzinfo=timezone.utc))
        snapshots = json.loads(self.upload.call_args.args[0])["snapshots"]
        self.assertEqual(snapshots[0], old)
        self.assertEqual(len(snapshots), 2)

    def test_read_failure_never_uploads_replacement(self):
        self.blob.exists.return_value = True
        with patch.dict("sys.modules", self.google_modules):
            from google.api_core.exceptions import GoogleAPIError
            self.blob.download_as_text.side_effect = GoogleAPIError("read failed")
            with self.assertRaisesRegex(StorageError, "read failed"):
                publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, datetime.now(timezone.utc))
        self.upload.assert_not_called()

    def test_concurrent_read_retries_before_upload(self):
        self.blob.exists.return_value = True
        with patch.dict("sys.modules", self.google_modules):
            from google.api_core.exceptions import PreconditionFailed
            self.blob.download_as_text.side_effect = [
                PreconditionFailed("generation changed during read"),
                json.dumps({"snapshots": []}),
            ]
            publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, datetime.now(timezone.utc))
        self.assertEqual(self.blob.download_as_text.call_count, 2)
        self.upload.assert_called_once()

    def test_persistent_concurrency_fails_without_unconditional_upload(self):
        with patch.dict("sys.modules", self.google_modules):
            from google.api_core.exceptions import PreconditionFailed
            self.upload.side_effect = PreconditionFailed("generation changed")
            with self.assertRaisesRegex(StorageError, "Conflitos concorrentes"):
                publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, datetime.now(timezone.utc))
        self.assertEqual(self.upload.call_count, 5)
        self.assertTrue(all(call.kwargs["if_generation_match"] == 0 for call in self.upload.call_args_list))

    def test_preserves_all_extractions_even_when_rows_are_identical(self):
        history = [{"extracted_at": f"2026-10-19T12:{minute:02}:00+00:00",
                    "rows": [typed_row(sample_row(), FIELDS)]} for minute in range(60)]
        self.blob.exists.return_value = True
        self.blob.download_as_text.return_value = json.dumps({"snapshots": history})
        with patch.dict("sys.modules", self.google_modules):
            publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"},
                         datetime(2026, 10, 19, 13, tzinfo=timezone.utc))
        snapshots = json.loads(self.upload.call_args.args[0])["snapshots"]
        self.assertEqual(snapshots[:-1], history)
        self.assertEqual(len(snapshots), 61)

    def test_invalid_json_never_uploads_replacement(self):
        self.blob.exists.return_value = True
        self.blob.download_as_text.return_value = "invalid JSON"
        with patch.dict("sys.modules", self.google_modules):
            with self.assertRaisesRegex(StorageError, "JSON publicado inválido"):
                publish_json([sample_row()], FIELDS, {"bucket": "test-bucket"}, datetime.now(timezone.utc))
        self.upload.assert_not_called()

    def test_cloud_storage_errors_are_reported(self):
        extracted_at = datetime.now(timezone.utc)
        with patch.dict("sys.modules", self.google_modules):
            from google.api_core.exceptions import GoogleAPIError
            self.upload.side_effect = GoogleAPIError("permission denied")
            with self.assertRaisesRegex(StorageError, "permission denied"):
                publish_json([sample_row()], FIELDS, {"bucket":"test-bucket"}, extracted_at)

    def source_file(self):
        import tempfile
        from pathlib import Path
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "abc123-secoes_eleitorais_alteradas_2t-pais_2026.csv.zip"
        path.write_bytes(b"PK\x03\x04zip")
        return path

    def test_archive_source_uploads_new_copy_with_source_metadata(self):
        version = {"url": "https://cdn.tse.jus.br/x/secoes_eleitorais_alteradas_2t-pais_2026.csv.zip", "sha256": "ab" * 32,
                   "last_modified": "Mon, 19 Oct 2026 14:12:23 GMT", "etag": '"3509"', "downloaded_at": "2026-10-20T18:00:00+00:00"}
        self.bucket.list_blobs = Mock(return_value=[])
        with patch.dict("sys.modules", self.google_modules):
            result = archive_source(self.source_file(), "changes", version, {"bucket": "test-bucket"})
        self.assertRegex(result, r"^test-bucket/fontes/changes/\d{8}T\d{12}Z-[a-f0-9]{32}-20261019T141223Z-abababababab-secoes_eleitorais_alteradas_2t-pais_2026\.csv\.zip$")
        self.bucket.list_blobs.assert_not_called()
        kwargs = self.blob.upload_from_filename.call_args.kwargs
        self.assertEqual(kwargs["if_generation_match"], 0)
        self.assertEqual(kwargs["content_type"], "application/zip")
        self.assertEqual(self.blob.metadata["sha256"], "ab" * 32)
        self.assertEqual(self.blob.metadata["source_url"], version["url"])
        self.assertIsNotNone(datetime.fromisoformat(self.blob.metadata["archived_at"]).utcoffset())
        self.assertIn("immutable", self.blob.cache_control)

    def test_archive_source_keeps_identical_copies_even_at_same_instant(self):
        existing = Mock(name="fontes/changes/20261018T000000Z-abababababab-old.zip", metadata={"sha256": "ab" * 32})
        existing.name = "fontes/changes/20261018T000000Z-abababababab-old.zip"
        self.bucket.list_blobs = Mock(return_value=[existing])
        path = self.source_file()
        version = {"sha256": "ab" * 32, "last_modified": "Mon, 19 Oct 2026 14:12:23 GMT"}
        with patch.dict("sys.modules", self.google_modules), patch("scripts.storage_io.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 21, 15, tzinfo=timezone.utc)
            first = archive_source(path, "changes", version, {"bucket": "test-bucket"})
            second = archive_source(path, "changes", version, {"bucket": "test-bucket"})
        self.assertNotEqual(first, second)
        self.assertEqual(self.blob.upload_from_filename.call_count, 2)
        self.bucket.list_blobs.assert_not_called()
        self.assertTrue(all(call.kwargs["if_generation_match"] == 0
                            for call in self.blob.upload_from_filename.call_args_list))

    def test_archive_source_requires_sha256_and_valid_config(self):
        with self.assertRaisesRegex(StorageError, "SHA-256"):
            archive_source(self.source_file(), "changes", {}, {"bucket": "test-bucket"})
        with self.assertRaisesRegex(StorageError, "archiveSources"):
            archive_sources({"archiveSources": "changes"})
        self.assertEqual(archive_sources({}), ("fontes", ["changes", "registry", "votes", "details"]))
        self.assertEqual(archive_sources({"archivePrefix": "/raw/", "archiveSources": []}), ("raw", []))


if __name__ == "__main__":
    unittest.main()
