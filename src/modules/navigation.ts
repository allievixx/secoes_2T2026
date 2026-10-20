import { $maybe } from "../utils/dom";

const SECTION_IDS = ["top", "sec-mapa", "sec-lista", "sec-uf", "sec-timeline", "sec-dados", "sec-sobre"];

/** Destaque do link ativo no header, com rolagem suave e acompanhamento do scroll. */
export function initializeNavigation(): void {
  const links = [...document.querySelectorAll<HTMLAnchorElement>(".nav a")];
  let holdUntil = 0;

  const setActive = (id: string) => {
    for (const a of links) {
      if (a.dataset.sec === id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
  };

  for (const a of links) {
    a.addEventListener("click", event => {
      event.preventDefault();
      const id = a.dataset.sec ?? "top";
      let el = $maybe(id);

      // Se o elemento não estiver no DOM (ex.: usuário na aba Linha do tempo clicando em Mapa ou Dados),
      // ativa a aba diária mais recente para remontar o painel completo.
      if (!el) {
        const dayTab = document.querySelector<HTMLButtonElement>('.snapshot-day .snapshot-tab');
        if (dayTab) {
          dayTab.click();
          el = $maybe(id);
        }
      }

      if (el instanceof HTMLDetailsElement) el.open = true;
      // Enquanto a rolagem suave acontece, o scroll listener não deve "roubar" o destaque.
      holdUntil = Date.now() + 1200;
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
      setActive(id);
    });
  }

  document.querySelector<HTMLAnchorElement>(".logo")?.addEventListener("click", event => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
    setActive("top");
  });

  window.addEventListener("scroll", () => requestAnimationFrame(() => {
    if (Date.now() < holdUntil) return;
    let current = "top";
    for (const id of SECTION_IDS) {
      const el = $maybe(id);
      if (el && el.getBoundingClientRect().top - 84 < innerHeight * .35) current = id;
    }
    setActive(current);
  }), { passive: true });
}
