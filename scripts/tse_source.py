"""Descobre o CSV vigente pelo fluxo público de geração de arquivos do SIG/TSE."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urlencode, urlsplit, urlunsplit

TSE_PAGE = "https://sig.tse.jus.br/ords/dwapr/r/seai/sig-eleicao-eleitorado/se%C3%A7%C3%B5es-alteradas"
LOGGER = logging.getLogger(__name__)


class DiscoveryError(ValueError):
    """Sem fonte vigente comprovada; nunca recorrer silenciosamente ao ZIP antigo."""


def fresh_page_url(page_url: str) -> str:
    parts = urlsplit(page_url)
    if parts.scheme != "https" or parts.netloc != "sig.tse.jus.br" or parts.path != urlsplit(TSE_PAGE).path:
        raise DiscoveryError("Página de descoberta deve ser a página oficial de seções alteradas do TSE")
    # Não reaproveitar sessões nem filtros recebidos de um navegador de usuário.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "clear=14&session=0", ""))


def validate_download(url: str, year: int, page_text: str) -> str:
    parts = urlsplit(url)
    pattern = rf"/estatistica/sead/odsele/arquivos_gerados/eleitorado_eleicao_{year}/(\d{{8}}_\d{{6}})/[a-f0-9]{{32}}/secoes_eleitorais_alteradas_2t-pais_{year}\.csv\.zip"
    match = re.fullmatch(pattern, parts.path)
    if parts.scheme != "https" or parts.netloc != "cdn.tse.jus.br" or not match or parts.query or parts.fragment:
        raise DiscoveryError("Link retornado não é o CSV nacional esperado do TSE")
    updated = re.search(r"Última atualização:\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}:\d{2})", page_text)
    if not updated:
        raise DiscoveryError("Página não informa a última atualização; não é possível comprovar a versão vigente")
    page_time = datetime.strptime(" ".join(updated.groups()), "%d.%m.%Y %H:%M")
    file_time = datetime.strptime(match[1], "%Y%m%d_%H%M%S")
    if file_time.replace(second=0) != page_time:
        raise DiscoveryError("Arquivo gerado não corresponde à última atualização exibida na página")
    return url


def discover_changes(page_url: str, year: int, timeout_ms: int = 180_000) -> dict[str, str]:
    """Navega em sessão nova, sem filtros, e retorna URL e evidências da descoberta."""
    start_url = fresh_page_url(page_url)
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError as exc:
        raise DiscoveryError("Instale playwright e seu Chromium para descobrir a fonte vigente") from exc

    try:
        LOGGER.info("TSE: iniciando driver Playwright")
        with sync_playwright() as playwright:
            LOGGER.info("TSE: iniciando Chromium com interface")
            # O portal aceita Chromium com interface; headless recebeu HTTP 403
            # mesmo com Google Chrome instalado. Em Linux usamos display Xvfb.
            browser = playwright.chromium.launch(headless=False, args=["--disable-dev-shm-usage"])
            LOGGER.info("TSE: Chromium iniciado; criando contexto e página")
            try:
                context = browser.new_context(locale="pt-BR")
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                LOGGER.info("TSE: abrindo página em sessão nova")
                response = page.goto(start_url, wait_until="domcontentloaded")
                LOGGER.info("TSE: resposta inicial HTTP %s", response.status if response else "sem resposta")
                if response is None or response.status >= 400:
                    raise DiscoveryError(f"Portal TSE indisponível ou acesso recusado (HTTP {response.status if response else 'sem resposta'}); publicação cancelada")
                # Uma sessão expirada/inexistente é redirecionada para home. Usar
                # a sessão recém-criada para abrir a página 14, nunca a do config.
                if page.locator('input[name="p_flow_step_id"]').input_value() != "14":
                    LOGGER.info("TSE: sessão criada; navegando para página 14")
                    session = page.locator('input[name="p_instance"]').input_value()
                    if not session.isdigit():
                        raise DiscoveryError("O portal não forneceu uma sessão válida")
                    parts = urlsplit(start_url)
                    response = page.goto(urlunsplit((parts.scheme, parts.netloc, parts.path,
                                          urlencode({"clear": "14", "session": session}), "")),
                              wait_until="domcontentloaded")
                    if response is None or response.status >= 400:
                        raise DiscoveryError("Portal TSE recusou a nova sessão; publicação cancelada")
                if page.locator('input[name="p_flow_step_id"]').input_value() != "14":
                    raise DiscoveryError("O portal não abriu a página de seções alteradas")
                page.get_by_role("button", name="Gerar arquivos", exact=True).wait_for()
                LOGGER.info("TSE: página 14 carregada; verificando filtros nacionais")
                text = page.locator("body").inner_text()
                for label in (f"Ano: {year}", "País: Todos", "Região: Todas", "UF: Todas",
                              "Município: Todos", "Zona: Todas", "Local de votação: Todos"):
                    if label not in text:
                        raise DiscoveryError(f"Filtro nacional esperado não confirmado: {label}")
                page.get_by_role("button", name="Gerar arquivos", exact=True).click()
                LOGGER.info("TSE: abrindo requisição de arquivos")
                frame = page.frame_locator("iframe")
                frame.locator("#P2_NOME_ARQUIVO").wait_for(state="attached")
                expected = f"secoes_eleitorais_alteradas_2t-pais_{year}"
                if frame.locator("#P2_NOME_ARQUIVO").input_value() != expected:
                    raise DiscoveryError("Nome da exportação não corresponde à lista nacional esperada")
                frame.locator('input[value="CSV_BR"]').check()
                frame.locator('input[value="CSV_US"]').uncheck()
                frame.locator('input[value="HTML"]').uncheck()
                frame.get_by_role("button", name="Gerar Arquivo", exact=True).click()
                LOGGER.info("TSE: aguardando link do CSV vigente")
                link = frame.get_by_role("link", name="Download", exact=True)
                link.wait_for(state="visible")
                url = link.get_attribute("href") or ""
                validate_download(url, year, text)
                LOGGER.info("TSE: link vigente validado")
                return {"url": url, "discovery_page": TSE_PAGE,
                        "page_updated": re.search(r"Última atualização:[^\n\\]+", text)[0].strip()}
            finally:
                LOGGER.info("TSE: encerrando Chromium")
                browser.close()
    except Error as exc:
        raise DiscoveryError(f"Falha na descoberta da fonte vigente no portal TSE: {exc}") from exc