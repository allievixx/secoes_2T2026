import unittest
from unittest.mock import MagicMock, patch

from scripts.gerar_dados import main
from scripts.tse_source import DiscoveryError, TSE_PAGE, discover_changes, fresh_page_url, validate_download

URL = "https://cdn.tse.jus.br/estatistica/sead/odsele/arquivos_gerados/eleitorado_eleicao_2026/20261021_141929/1d5a9ea9d39198eb5b3cf54312a93675/secoes_eleitorais_alteradas_2t-pais_2026.csv.zip"
TEXT = "Ano: 2026 País: Todos Região: Todas UF: Todas Município: Todos Zona: Todas Local de votação: Todos\nÚltima atualização: 21.10.2026 - 14:19"


class DiscoveryTest(unittest.TestCase):
    def test_removes_user_session_and_filters(self):
        self.assertEqual(fresh_page_url(TSE_PAGE + "?session=123&P0_UF=SP"), TSE_PAGE + "?clear=14&session=0")

    def test_rejects_external_page(self):
        with self.assertRaises(DiscoveryError):
            fresh_page_url("https://example.org/page")

    def test_accepts_current_national_download(self):
        self.assertEqual(validate_download(URL, 2026, TEXT), URL)

    def test_rejects_stale_link_wrong_year_host_and_format(self):
        for url in (URL.replace('20261021_141929', '20261019_105000'),
                    URL.replace('cdn.tse.jus.br', 'example.org'),
                    URL.replace('2026', '2022'), URL.replace('.csv.zip', '.html.zip'), URL + '?x=1'):
            with self.subTest(url=url), self.assertRaises(DiscoveryError):
                validate_download(url, 2026, TEXT)

    def test_rejects_missing_update_time(self):
        with self.assertRaises(DiscoveryError):
            validate_download(URL, 2026, 'home')

    def test_browser_workflow_and_cleanup(self):
        with patch('playwright.sync_api.sync_playwright') as factory:
            browser = factory.return_value.__enter__.return_value.chromium.launch.return_value
            page = browser.new_context.return_value.new_page.return_value
            page.goto.return_value.status = 200
            def locator(selector):
                result = MagicMock()
                if selector == 'input[name="p_flow_step_id"]':
                    result.input_value.return_value = '14'
                elif selector == 'body':
                    result.inner_text.return_value = TEXT
                return result
            page.locator.side_effect = locator
            frame = page.frame_locator.return_value
            frame.locator.return_value.input_value.return_value = 'secoes_eleitorais_alteradas_2t-pais_2026'
            frame.get_by_role.return_value.get_attribute.return_value = URL
            self.assertEqual(discover_changes(TSE_PAGE, 2026)['url'], URL)
            factory.return_value.__enter__.return_value.chromium.launch.assert_called_once_with(
                headless=False, args=['--disable-dev-shm-usage'])
            browser.close.assert_called_once()

    def test_http_denied_fails_fast_and_closes_browser(self):
        with patch('playwright.sync_api.sync_playwright') as factory:
            browser = factory.return_value.__enter__.return_value.chromium.launch.return_value
            page = browser.new_context.return_value.new_page.return_value
            page.goto.return_value.status = 403
            with self.assertRaisesRegex(DiscoveryError, 'HTTP 403'):
                discover_changes(TSE_PAGE, 2026)
            browser.close.assert_called_once()

    def test_failed_discovery_never_downloads_or_publishes(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        with patch('scripts.gerar_dados.discover_changes', side_effect=DiscoveryError('portal indisponível')), \
             patch('scripts.gerar_dados.download') as download, \
             patch('scripts.gerar_dados.publish_json') as publish:
            self.assertEqual(main(['--config', str(root / 'pipeline-config.json'), '--inspect']), 1)
        download.assert_not_called()
        publish.assert_not_called()

    def test_inspect_downloads_discovered_url_not_configured_fallback(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        discovery = {'url': URL, 'discovery_page': TSE_PAGE, 'page_updated': '21.10.2026 - 14:19'}
        row = {'QT_ELEITORES': '100'}
        with patch('scripts.gerar_dados.discover_changes', return_value=discovery), \
             patch('scripts.gerar_dados.download') as download, \
             patch('scripts.gerar_dados.load_changes', return_value={('AM', 'MANAUS', 1, 1): row}), \
             patch('scripts.gerar_dados.publish_json') as publish:
            self.assertEqual(main(['--config', str(root / 'pipeline-config.json'), '--inspect']), 0)
        self.assertEqual(download.call_args.args[0], URL)
        publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()