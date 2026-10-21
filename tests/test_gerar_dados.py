"""Fixtures sintéticas dos schemas oficiais; nunca lê o CSV existente."""

import csv
import gzip
import io
import http.client
import json
import ssl
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import zipfile

from scripts.gerar_dados import (
    CHANGES, FIELDS, REGISTRY, RESULT_KEY, DataError, build_rows, coordinate,
    download, haversine, iter_csv, load_changes, load_ibge, load_registry, load_results,
    main, normalize, source_version, write_output,
)
from scripts.storage_io import StorageError


def csv_bytes(rows, encoding="cp1252"):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, list(rows[0]), delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode(encoding)


def changed(section="1", **overrides):
    return dict.fromkeys(CHANGES, "") | {
        "AA_ELEICAO":"2026", "SG_UF":"AL", "NM_MUNICIPIO":"CAMPO GRANDE",
        "NR_ZONA":"20", "NR_SECAO":section, "NM_LOCAL_VOTACAO_INICIAL":"Escola Antiga",
        "NM_LOCAL_VOTACAO_FINAL":"Escola Nova", "QT_ELEITORES":"400",
    } | overrides


def registry(section="1", old=False, **overrides):
    return dict.fromkeys(REGISTRY, "") | {
        "AA_ELEICAO":"2026", "NR_TURNO":"2", "SG_UF":"AL", "CD_MUNICIPIO":"27596",
        "NM_MUNICIPIO":"CAMPO GRANDE", "NR_ZONA":"20", "NR_SECAO":section,
        "NR_LOCAL_VOTACAO":"10" if old else "20",
        "NM_LOCAL_VOTACAO":"Escola Antiga" if old else "Escola Nova",
        "DS_ENDERECO":"Rua A; nº 1" if old else "Rua B", "NM_BAIRRO":"Centro",
        "NR_LATITUDE":"-9.96" if old else "-9.95", "NR_LONGITUDE":"-36.79",
        "NR_LOCAL_VOTACAO_ORIGINAL":"10", "NM_LOCAL_VOTACAO_ORIGINAL":"Escola Antiga",
        "DS_ENDERECO_LOCVT_ORIGINAL":"Rua A; nº 1",
    } | overrides


def election(**overrides):
    return dict.fromkeys(RESULT_KEY, "") | {
        "ANO_ELEICAO":"2026", "NR_TURNO":"1", "CD_CARGO":"1", "SG_UF":"AL",
        "CD_MUNICIPIO":"27596", "NR_ZONA":"20", "NR_SECAO":"1",
    } | overrides


def municipalities():
    return [{"id":2701506, "nome":"Campo Grande", "microrregiao":{"mesorregiao":{"UF":{"sigla":"AL"}}}}]


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, name, rows):
        path = self.root / name
        if name.endswith(".zip"):
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("dados.csv", csv_bytes(rows))
        else:
            path.write_bytes(csv_bytes(rows))
        return path

    def test_normalization_and_geodesic_distance(self):
        self.assertEqual(normalize("São João-d'Aliança"), "SAOJOAODALIANCA")
        self.assertAlmostEqual(haversine((0, 0), (0, 1)), 111.195, places=3)
        self.assertIsNone(haversine(None, (0, 0)))
        self.assertEqual(coordinate("-9,96", True), -9.96)
        self.assertIsNone(coordinate("-1", True))
        with self.assertRaises(DataError):
            coordinate("100", True)

    def test_lowercase_header_encoding_and_quoted_semicolon(self):
        row = {k.lower():v for k,v in changed().items()}
        row["nm_local_votacao_inicial"] = 'Escola São José; "anexo"'
        source = self.source("changes.zip", [row])
        changes = load_changes(source, "cp1252", 2026)
        self.assertEqual(next(iter(changes.values()))["NM_LOCAL_VOTACAO_INICIAL"], row["nm_local_votacao_inicial"])

    def test_avoids_national_and_state_double_count(self):
        path = self.root / "registry.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("cadastro_AL.csv", csv_bytes([registry()]))
            archive.writestr("cadastro_BRASIL.csv", csv_bytes([registry()]))
        self.assertEqual(len(list(iter_csv(path, REGISTRY))), 1)

    def test_changes_excludes_national_rows_without_destination_and_logs_count(self):
        rows = [changed(), changed("2", NM_LOCAL_VOTACAO_FINAL=""),
                changed("3", NM_LOCAL_VOTACAO_FINAL="   "),
                changed("4", NM_LOCAL_VOTACAO_FINAL="", SG_UF="ZZ")]
        with self.assertLogs("gerar_dados", level="INFO") as logs:
            changes = load_changes(self.source("national.csv", rows), "cp1252", 2026)
        self.assertEqual(list(changes), [("AL", "CAMPOGRANDE", 20, 1)])
        self.assertIn("3 seções sem local final", logs.output[-1])
        self.assertIn("1 alterações com destino informado", logs.output[-1])

    def test_changes_without_any_destination_preserves_empty_publication_guard(self):
        with self.assertRaisesRegex(DataError, "Nenhuma seção alterada"):
            load_changes(self.source("empty.csv", [changed(NM_LOCAL_VOTACAO_FINAL="")]), "cp1252", 2026)

    def test_invalid_schema_and_duplicate_changes(self):
        with self.assertRaisesRegex(DataError, "colunas ausentes"):
            list(iter_csv(self.source("bad.csv", [{"a":"b"}]), CHANGES))
        with self.assertRaisesRegex(DataError, "duplicada"):
            load_changes(self.source("duplicate.csv", [changed(), changed()]), "cp1252", 2026)

    def test_registry_different_turns_selects_second_in_either_order(self):
        changes = load_changes(self.source("changes.csv", [changed()]), "cp1252", 2026)
        first = registry(NR_TURNO="1", NR_LOCAL_VOTACAO="1627", DS_ENDERECO="Rua A",
                         NR_LATITUDE="-25,3430183", NR_LONGITUDE="-49,2529433")
        second = registry(NR_LOCAL_VOTACAO="1635", DS_ENDERECO="Rua A, S/N",
                          NR_LATITUDE="-1", NR_LONGITUDE="-1")
        for records in ([first, second], [second, first], [second, second, first]):
            with self.subTest(turns=[r["NR_TURNO"] for r in records]):
                sections, _, _, _ = load_registry(self.source("registry.csv", records), changes, "cp1252", 2026)
                self.assertEqual(sections[("AL", "27596", 20, 1)], second)

    def test_registry_same_turn_conflict_strict_mode_still_fails(self):
        changes = load_changes(self.source("changes.csv", [changed()]), "cp1252", 2026)
        source = self.source("conflicting.csv", [registry(), registry(DS_ENDERECO="Outro endereço")])
        with self.assertRaises(DataError) as caught:
            load_registry(source, changes, "cp1252", 2026)
        message = str(caught.exception)
        self.assertIn("Cadastro conflitante para seção: ('AL', '27596', 20, 1)", message)

    def test_registry_conflict_partial_mode_preserves_section_and_votes_without_location(self):
        for records in ([registry(), registry(DS_ENDERECO="Outro endereço")],
                        [registry(DS_ENDERECO="Outro endereço"), registry()]):
            changes = load_changes(self.source("changes.csv", [changed()]), "cp1252", 2026)
            sections, locations, names, places = load_registry(
                self.source("registry.csv", records), changes, "cp1252", 2026, allow_incomplete=True)
            k = ("AL", "27596", 20, 1)
            rows, issues = build_rows(changes, sections, locations, names,
                                     {("AL", "CAMPOGRANDE"):2701506}, {k:{"aptos_1t":350}}, {}, places)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["eleitores"], 400)
            self.assertEqual(rows[0]["aptos_1t"], 350)
            self.assertEqual(rows[0]["local_2t"], "Escola Nova")
            for field in ("endereco_1t", "endereco_2t", "lat_1t", "lon_1t", "lat_2t", "lon_2t", "distancia_km"):
                self.assertEqual(rows[0][field], "")
            self.assertIn("cadastro conflitante", issues[0])
            self.assertFalse(locations)

    def test_registry_second_turn_supersedes_partial_first_turn_conflict(self):
        changes = load_changes(self.source("changes.csv", [changed()]), "cp1252", 2026)
        records = [registry(NR_TURNO="1"), registry(NR_TURNO="1", DS_ENDERECO="Outro"), registry()]
        sections, _, _, _ = load_registry(self.source("registry.csv", records), changes, "cp1252", 2026, allow_incomplete=True)
        self.assertEqual(sections[("AL", "27596", 20, 1)], registry())

    def test_ibge_gzip_and_immediate_region_fallback(self):
        rows = municipalities()
        rows[0]["microrregiao"] = None
        rows[0]["regiao-imediata"] = {"regiao-intermediaria":{"UF":{"sigla":"AL"}}}
        path = self.root / "ibge.json"
        path.write_bytes(gzip.compress(json.dumps(rows).encode()))
        self.assertEqual(load_ibge(path, {})[("AL", "CAMPOGRANDE")], 2701506)

    def fixtures(self, retain_old=True, registry_rows=None):
        changes = load_changes(self.source("changes.zip", [changed()]), "cp1252", 2026)
        rows = registry_rows if registry_rows is not None else [registry()] + ([registry("2", old=True)] if retain_old else [])
        sections, locations, names, places = load_registry(self.source("registry.zip", rows), changes, "cp1252", 2026)
        k = ("AL", "27596", 20, 1)
        results = {k:{"aptos_1t":350, "abstencao_1t":70, "lula_1t":150, "flavio_1t":100, "outros_1t":20, "brancos_1t":5, "nulos_1t":5}}
        return changes, sections, locations, names, {("AL", "CAMPOGRANDE"):2701506}, results, places

    def build(self, args, distances):
        changes, sections, locations, names, ibge, results, places = args
        return build_rows(changes, sections, locations, names, ibge, results, distances, places)

    def test_build_rows_full_join(self):
        args = self.fixtures()
        rows, issues = self.build(args, {("AL", "27596", 20, "20"):5.0})
        self.assertFalse(issues)
        self.assertEqual(list(rows[0]), FIELDS)
        self.assertEqual(rows[0]["eleitores"], 400)
        self.assertEqual(rows[0]["aptos_1t"], 350)
        self.assertTrue(rows[0]["regiao_longe_da_urna"])
        self.assertEqual(rows[0]["distancia_km"], 1.112)
        self.assertEqual(rows[0]["endereco_1t"], "Rua A; nº 1")

    def test_old_local_without_sections_has_no_invented_coordinates(self):
        args = self.fixtures(retain_old=False)
        rows, issues = self.build(args, {("AL", "27596", 20, "20"):1.0})
        self.assertFalse(issues)
        self.assertEqual(rows[0]["lat_1t"], "")
        self.assertEqual(rows[0]["distancia_km"], "")
        self.assertEqual(rows[0]["endereco_1t"], "Rua A; nº 1")

    def test_missing_enrichments_stay_unknown_not_false(self):
        rows, issues = self.build(self.fixtures(), {})
        self.assertFalse(issues)
        self.assertEqual(rows[0]["regiao_longe_da_urna"], "")

    def test_ambiguous_locations_partial_mode_preserves_votes_and_safe_fields(self):
        for old in (True, False):
            with self.subTest(old=old):
                records = [registry(), registry("2", old=True)]
                if old:
                    records.append(registry("3", old=True, NR_LATITUDE="-9.80"))
                else:
                    records[0] = registry(NM_LOCAL_VOTACAO="Outro local")
                    records.extend([registry("3"), registry("4", NR_LATITUDE="-9.80")])
                changes, sections, locations, names, ibge, results, places = self.fixtures(registry_rows=records)
                with self.assertRaisesRegex(DataError, "Local ambíguo"):
                    build_rows(changes, sections, locations, names, ibge, results, {}, places)
                rows, issues = build_rows(
                    changes, sections, locations, names, ibge, results, {}, places,
                    allow_incomplete=True)
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["eleitores"], 400)
                self.assertEqual(row["lula_1t"], 150)
                self.assertEqual(row["distancia_km"], "")
                ambiguous, safe = ("1t", "2t") if old else ("2t", "1t")
                self.assertEqual(row[f"lat_{ambiguous}"], "")
                self.assertEqual(row[f"lon_{ambiguous}"], "")
                self.assertNotEqual(row[f"lat_{safe}"], "")
                self.assertTrue(any("Local ambíguo" in issue for issue in issues))
                if not old:
                    self.assertEqual(row["endereco_2t"], "")
                    self.assertEqual(row["bairro_2t"], "")

    def stale_registry(self, **overrides):
        """Linha de 2º turno que o TSE ainda não atualizou: local atual é o antigo e o novo está só em *_ORIGINAL."""
        return registry(old=True, NR_LOCAL_VOTACAO_ORIGINAL="20", NM_LOCAL_VOTACAO_ORIGINAL="Escola Nova",
                        DS_ENDERECO_LOCVT_ORIGINAL="Rua B (original)", **overrides)

    def test_final_local_only_in_original_columns_uses_same_zone_place_from_any_turn(self):
        # A seção 7 estava na Escola Nova (id 20) no 1º turno e vai para a Antiga no 2º: a Escola Nova só aparece
        # em linha de 1º turno, fora do índice por nome, mas o id na mesma zona a identifica com segurança.
        other = [registry("7", NR_TURNO="1"), registry("7", old=True)]
        rows, issues = self.build(self.fixtures(registry_rows=[self.stale_registry(), *other]), {("AL", "27596", 20, "20"):5.0})
        self.assertFalse(issues)
        self.assertEqual(rows[0]["endereco_2t"], "Rua B")
        self.assertEqual(rows[0]["bairro_2t"], "Centro")
        self.assertEqual(rows[0]["lat_2t"], -9.95)
        self.assertEqual(rows[0]["endereco_1t"], "Rua A; nº 1")
        self.assertEqual(rows[0]["lat_1t"], -9.96)
        self.assertEqual(rows[0]["distancia_km"], 1.112)
        self.assertTrue(rows[0]["regiao_longe_da_urna"])

    def test_final_local_id_in_another_zone_or_with_other_name_is_not_trusted(self):
        # NR_LOCAL_VOTACAO se repete entre zonas: id 20 na zona 21 é outro lugar.
        for decoy in [registry("7", NR_ZONA="21", NR_TURNO="1"), registry("7", NR_TURNO="1", NM_LOCAL_VOTACAO="Ginásio")]:
            rows, issues = self.build(self.fixtures(registry_rows=[self.stale_registry(), decoy]), {})
            self.assertEqual(len(issues), 1, decoy["NM_LOCAL_VOTACAO"])
            self.assertIn("sem coordenadas", issues[0])
            self.assertEqual(rows[0]["endereco_2t"], "Rua B (original)")
            self.assertEqual(rows[0]["lat_2t"], "")

    def test_final_local_only_in_original_columns_without_coordinates_keeps_address(self):
        rows, issues = self.build(self.fixtures(registry_rows=[self.stale_registry()]), {})
        self.assertEqual(len(issues), 1)
        self.assertIn("sem coordenadas", issues[0])
        self.assertEqual(rows[0]["endereco_2t"], "Rua B (original)")
        self.assertEqual(rows[0]["lat_2t"], "")
        self.assertEqual(rows[0]["distancia_km"], "")

    def test_final_local_only_in_original_columns_with_ambiguous_coordinates_stays_empty(self):
        twins = [registry("7", NR_TURNO="1"), registry("7", old=True), registry("8", NR_TURNO="1", NR_LATITUDE="-9.80"), registry("8", old=True)]
        rows, issues = self.build(self.fixtures(registry_rows=[self.stale_registry(), *twins]), {})
        self.assertEqual(len(issues), 1)
        self.assertIn("ambíguas", issues[0])
        self.assertEqual(rows[0]["endereco_2t"], "Rua B (original)")
        self.assertEqual(rows[0]["lat_2t"], "")

    def test_final_local_absent_everywhere_is_reported(self):
        rows, issues = self.build(self.fixtures(registry_rows=[registry(old=True)]), {})
        self.assertEqual(len(issues), 1)
        self.assertIn("não encontrado", issues[0])
        self.assertEqual(rows[0]["endereco_2t"], "")

    def test_download_records_source_version_and_cache_hit_reuses_it(self):
        payload = b"abc;def\n1;2\n"
        headers = {"Content-Length": str(len(payload)), "Last-Modified": "Tue, 20 Oct 2026 00:05:46 GMT", "ETag": '"a9a53db"'}

        class FakeResponse(io.BytesIO):
            def __init__(self):
                super().__init__(payload)
                self.headers = headers
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                self.close()

        cache = self.root / "cache"
        with patch("scripts.gerar_dados.urllib.request.urlopen", return_value=FakeResponse()) as opened:
            path = download("https://example.test/registry.zip", cache)
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(download("https://example.test/registry.zip", cache), path)
            self.assertEqual(opened.call_count, 1)
        version = source_version(path)
        self.assertEqual(version["last_modified"], headers["Last-Modified"])
        self.assertEqual(version["etag"], headers["ETag"])
        self.assertEqual(version["sha256"], __import__("hashlib").sha256(payload).hexdigest())
        self.assertEqual(version["bytes"], len(payload))
        local = self.root / "local.csv"
        local.write_bytes(payload)
        self.assertEqual(source_version(local), {"sha256": version["sha256"], "bytes": len(payload)})

    def test_download_retries_ssl_handshake_timeout_then_succeeds(self):
        response = io.BytesIO(b"complete")
        response.headers = {"Content-Length": "8"}
        failure = urllib.error.URLError(TimeoutError("The handshake operation timed out"))
        with patch("scripts.gerar_dados.urllib.request.urlopen", side_effect=[failure, response]) as opened, \
             patch("scripts.gerar_dados.time.sleep") as sleep, \
             self.assertLogs("gerar_dados", level="WARNING") as logs:
            path = download("https://example.test/source.zip", self.root / "cache")
        self.assertEqual(path.read_bytes(), b"complete")
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(2)
        self.assertIn("tentativa 1/3", logs.output[0])
        self.assertIn("https://example.test/source.zip", logs.output[0])
        self.assertEqual(source_version(path)["bytes"], 8)

    def test_download_timeout_exhaustion_preserves_cache_and_cleans_partial_files(self):
        cache = self.root / "cache"
        cache.mkdir()
        source = "https://example.test/source.zip"
        destination = cache / (__import__("hashlib").sha256(source.encode()).hexdigest()[:16] + "-source.zip")
        destination.write_bytes(b"previous")
        metadata = destination.with_name(destination.name + ".meta.json")
        metadata.write_text('{"sha256":"previous"}')
        response = io.BytesIO(b"partial")
        response.headers = {}
        response.read = unittest.mock.Mock(side_effect=[b"partial", TimeoutError("read timed out")])
        with patch("scripts.gerar_dados.urllib.request.urlopen",
                   side_effect=[response, TimeoutError("timed out"), TimeoutError("timed out")]) as opened, \
             patch("scripts.gerar_dados.time.sleep") as sleep, \
             self.assertLogs("gerar_dados", level="WARNING"):
            with self.assertRaises(TimeoutError):
                download(source, cache, refresh=True)
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(2), unittest.mock.call(4)])
        self.assertEqual(destination.read_bytes(), b"previous")
        self.assertEqual(metadata.read_text(), '{"sha256":"previous"}')
        self.assertEqual(set(cache.iterdir()), {destination, metadata})

    def test_download_does_not_retry_certificate_or_http_errors(self):
        failures = [
            urllib.error.URLError(ssl.SSLCertVerificationError("invalid certificate")),
            urllib.error.HTTPError("https://example.test/source.zip", 404, "Not Found", {}, None),
        ]
        for failure in failures:
            with self.subTest(failure=failure), \
                 patch("scripts.gerar_dados.urllib.request.urlopen", side_effect=failure) as opened, \
                 patch("scripts.gerar_dados.time.sleep") as sleep:
                with self.assertRaises(urllib.error.URLError):
                    download("https://example.test/source.zip", self.root / "cache")
                self.assertEqual(opened.call_count, 1)
                sleep.assert_not_called()

    def test_download_retries_truncation_with_fresh_digest_and_cleans_partial(self):
        for protocol_error in (False, True):
            with self.subTest(protocol_error=protocol_error):
                cache = self.root / str(protocol_error)
                partial = io.BytesIO(b"part")
                partial.headers = {"Content-Length": "8"}
                if protocol_error:
                    partial.read = unittest.mock.Mock(
                        side_effect=[b"part", http.client.IncompleteRead(b"", 4)])
                complete = io.BytesIO(b"complete")
                complete.headers = {"Content-Length": "8"}
                with patch("scripts.gerar_dados.urllib.request.urlopen",
                           side_effect=[partial, complete]) as opened, \
                     patch("scripts.gerar_dados.time.sleep") as sleep, \
                     self.assertLogs("gerar_dados", level="WARNING") as logs:
                    path = download("https://example.test/source.zip", cache)
                self.assertEqual(path.read_bytes(), b"complete")
                self.assertEqual(opened.call_count, 2)
                sleep.assert_called_once_with(2)
                self.assertIn("Download incompleto", logs.output[0])
                if not protocol_error:
                    self.assertIn("esperado=8 bytes, recebido=4 bytes", logs.output[0])
                version = source_version(path)
                self.assertEqual(version["bytes"], 8)
                self.assertEqual(version["sha256"], __import__("hashlib").sha256(b"complete").hexdigest())
                self.assertEqual(set(cache.iterdir()), {path, path.with_name(path.name + ".meta.json")})

    def test_download_truncation_exhaustion_preserves_cache_and_metadata(self):
        cache = self.root / "cache"
        source = "https://example.test/source.zip"
        original = io.BytesIO(b"previous")
        original.headers = {"Content-Length": "8"}
        with patch("scripts.gerar_dados.urllib.request.urlopen", return_value=original):
            path = download(source, cache)
        metadata = path.with_name(path.name + ".meta.json")
        previous_metadata = metadata.read_bytes()
        responses = [io.BytesIO(b"part") for _ in range(3)]
        for response in responses:
            response.headers = {"Content-Length": "8"}
        with patch("scripts.gerar_dados.urllib.request.urlopen", side_effect=responses) as opened, \
             patch("scripts.gerar_dados.time.sleep") as sleep, \
             self.assertLogs("gerar_dados", level="WARNING"):
            with self.assertRaisesRegex(DataError, "esperado=8 bytes, recebido=4 bytes"):
                download(source, cache, refresh=True)
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(2), unittest.mock.call(4)])
        self.assertEqual(path.read_bytes(), b"previous")
        self.assertEqual(metadata.read_bytes(), previous_metadata)
        self.assertEqual(set(cache.iterdir()), {path, metadata})

    def test_download_incomplete_read_exhaustion_reports_data_error(self):
        responses = [io.BytesIO(b"") for _ in range(3)]
        for response in responses:
            response.headers = {}
            response.read = unittest.mock.Mock(side_effect=http.client.IncompleteRead(b"part", 4))
        cache = self.root / "cache"
        with patch("scripts.gerar_dados.urllib.request.urlopen", side_effect=responses) as opened, \
             patch("scripts.gerar_dados.time.sleep"), \
             self.assertLogs("gerar_dados", level="WARNING"):
            with self.assertRaisesRegex(DataError, "Download incompleto: https://example.test/source.zip") as caught:
                download("https://example.test/source.zip", cache)
        self.assertIsInstance(caught.exception.__cause__, http.client.IncompleteRead)
        self.assertEqual(opened.call_count, 3)
        self.assertFalse(list(cache.iterdir()))

    def test_results_turn_office_filter_and_duplicate_protection(self):
        counts = {"13":150, "22":100, "12":20, "95":5, "96":5}
        rows = [election(NR_VOTAVEL=n, QT_VOTOS=str(q)) for n,q in counts.items()]
        rows += [election(NR_TURNO="2", NR_VOTAVEL="13", QT_VOTOS="999"), rows[0]]
        votes = self.source("votes.zip", rows)
        detail = election(QT_APTOS="350", QT_ABSTENCOES="70", QT_VOTOS_BRANCOS="5", QT_VOTOS_NULOS="5")
        details = self.source("details.zip", [detail, detail])
        k = ("AL", "27596", 20, 1)
        result = load_results(votes, details, {k}, "cp1252", 2026, "13", "22")
        self.assertEqual(result[k]["lula_1t"], 150)
        self.assertEqual(result[k]["outros_1t"], 20)
        bad = self.source("conflicting.zip", rows + [election(NR_VOTAVEL="13", QT_VOTOS="1")])
        with self.assertRaisesRegex(DataError, "conflitantes"):
            load_results(bad, details, {k}, "cp1252", 2026, "13", "22")

    def test_cli_end_to_end_and_overwrite_protection(self):
        self.source("changes.zip", [changed()])
        self.source("registry.zip", [registry(), registry("2", old=True)])
        self.source("votes.zip", [election(NR_VOTAVEL=n, QT_VOTOS=q) for n,q in [("13","150"),("22","100"),("12","20"),("95","5"),("96","5")]])
        self.source("details.zip", [election(QT_APTOS="350", QT_ABSTENCOES="70", QT_VOTOS_BRANCOS="5", QT_VOTOS_NULOS="5")])
        (self.root / "ibge.json").write_text(json.dumps(municipalities()), encoding="utf-8")
        self.source("long.csv", [{"UF":"AL", "CD_MUNICIPIO":"27596", "ZONA":"20", "NR_LOCAL_VOTACAO":"20", "DISTANCIA_MEDIA_KM":"5"}])
        config = self.root / "config.json"
        config.write_text(json.dumps({"storage":{"bucket":"test-bucket","object":"snapshot.json","archiveSources":["changes"]},"sources":{
            "changes":"changes.zip", "registry":"registry.zip", "votes":"votes.zip", "details":"details.zip",
            "municipalities":"ibge.json", "longDistance":"long.csv",
        }}), encoding="utf-8")
        output, report = self.root / "out.csv", self.root / "report.json"
        args = ["--destination","csv","--config",str(config),"--output",str(output),"--report",str(report)]
        self.assertEqual(main(args), 0)
        with output.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            self.assertEqual(reader.fieldnames, FIELDS)
            row = next(reader)
            self.assertEqual(row["regiao_longe_da_urna"], "True")
            self.assertEqual(row["endereco_1t"], "Rua A; nº 1")
        original = output.read_bytes()
        self.assertEqual(main(args), 1)
        self.assertEqual(output.read_bytes(), original)
        self.assertTrue(json.loads(report.read_text())["publicado"])
        # O destino padrão é Cloud Storage e não depende dos dois enriquecimentos adiados.
        content = json.loads(config.read_text())
        content["sources"]["longDistance"] = None
        config.write_text(json.dumps(content),encoding="utf-8")
        with patch("scripts.gerar_dados.publish_json",return_value="test-bucket/snapshot.json") as mocked_json, \
             patch("scripts.gerar_dados.archive_source",return_value="test-bucket/fontes/changes/20261019T141223Z-abc-changes.zip") as mocked_archive:
            self.assertEqual(main(["--config",str(config),"--report",str(report)]),0)
            self.assertEqual(mocked_json.call_args.args[0][0]["regiao_longe_da_urna"],"")
            self.assertEqual(mocked_json.call_count,1)
            self.assertEqual(output.read_bytes(),original)
            saved_report = json.loads(report.read_text())
            self.assertEqual(mocked_json.call_args.args[3].isoformat(),saved_report["generated_at"])
            self.assertEqual(saved_report["destination"],"storage")
            self.assertEqual(saved_report["storage_object"],"test-bucket/snapshot.json")
            self.assertEqual(saved_report["dashboard_data_url"],"https://storage.googleapis.com/test-bucket/snapshot.json")
            # Todas as fontes do TSE são arquivadas; IBGE não faz parte dessa lista.
            self.assertEqual(mocked_archive.call_count,4)
            self.assertEqual([call.args[1] for call in mocked_archive.call_args_list],
                             ["changes", "registry", "votes", "details"])
            self.assertEqual(len(mocked_archive.call_args.args[2]["sha256"]),64)
            self.assertEqual(saved_report["source_versions"]["changes"]["archived"],"test-bucket/fontes/changes/20261019T141223Z-abc-changes.zip")
            self.assertEqual(mocked_json.call_args.args[4]["changes"]["archived"],saved_report["source_versions"]["changes"]["archived"])
            self.assertIn("archived",saved_report["source_versions"]["registry"])
            self.assertNotIn("archived",saved_report["source_versions"]["municipalities"])

        # Falha ao arquivar não impede a publicação do dashboard, mas fica no relatório.
        with patch("scripts.gerar_dados.publish_json",return_value="test-bucket/snapshot.json") as mocked_json, \
             patch("scripts.gerar_dados.archive_source",side_effect=StorageError("sem permissao no bucket")):
            self.assertEqual(main(["--config",str(config),"--report",str(report)]),0)
            self.assertEqual(mocked_json.call_count,1)
            saved_report = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(saved_report["falhas_arquivamento"],["sem permissao no bucket"] * 4)
            self.assertTrue(saved_report["publicado"])

        content["allowIncomplete"] = True
        config.write_text(json.dumps(content), encoding="utf-8")
        incomplete_row = dict.fromkeys(FIELDS, "") | {
            "uf":"PE", "municipio":"Recife", "cd_ibge":2611606, "zona":3,
            "secao":735, "eleitores":250,
        }
        with patch("scripts.gerar_dados.build_rows",return_value=([incomplete_row],["Missing final location"])) as mocked_build, \
             patch("scripts.gerar_dados.archive_source",return_value="test-bucket/fontes/changes/x.zip"), \
             patch("scripts.gerar_dados.publish_json",return_value="test-bucket/snapshot.json") as mocked_json:
            self.assertEqual(main(["--config",str(config),"--report",str(report)]),0)
            self.assertTrue(mocked_build.call_args.kwargs["allow_incomplete"])
            self.assertEqual(mocked_json.call_args.args[0],[incomplete_row])
            saved_report = json.loads(report.read_text())
            self.assertTrue(saved_report["allow_incomplete"])
            self.assertEqual(saved_report["pendencias"],["Missing final location"])
            self.assertTrue(saved_report["publicado"])


if __name__ == "__main__":
    unittest.main()