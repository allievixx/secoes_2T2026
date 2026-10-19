import json
from types import ModuleType
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from scripts.gerar_dados import FIELDS
from scripts.storage_io import StorageError, publish_json, typed_row


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

        exceptions.GoogleAPIError = GoogleAPIError
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
        with patch.dict("sys.modules", self.google_modules):
            result = publish_json([sample_row()], FIELDS, {
                "bucket": "test-bucket", "object": "dash/snapshot.json",
            }, extracted_at)
        self.assertEqual(result, "test-bucket/dash/snapshot.json")
        self.bucket.blob.assert_called_once_with("dash/snapshot.json")
        args, kwargs = self.upload.call_args
        payload = json.loads(args[0])
        snapshot = payload["snapshots"][0]
        self.assertEqual(snapshot["extracted_at"], extracted_at.isoformat())
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

    def test_rejects_naive_extraction_timestamp(self):
        with self.assertRaisesRegex(StorageError, "fuso horário"):
            publish_json([sample_row()], FIELDS, {"bucket":"test-bucket"}, datetime(2026, 10, 19))

    def test_cloud_storage_errors_are_reported(self):
        extracted_at = datetime.now(timezone.utc)
        with patch.dict("sys.modules", self.google_modules):
            from google.api_core.exceptions import GoogleAPIError
            self.upload.side_effect = GoogleAPIError("permission denied")
            with self.assertRaisesRegex(StorageError, "permission denied"):
                publish_json([sample_row()], FIELDS, {"bucket":"test-bucket"}, extracted_at)


if __name__ == "__main__":
    unittest.main()
