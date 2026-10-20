import type { AreaCollection, DashboardData, EnrichedGroup, WinnerFilter } from "../../types";
import { CODEOF } from "../../utils/constants";
import { $, unescapeHTML } from "../../utils/dom";
import { int } from "../../utils/format";
import { renderCard } from "./card";
import { renderList } from "./list";
import { areaCode, createMap } from "./map";
import { DashboardState, enrichGroups } from "./state";
import { renderSummary } from "./summary";
import { renderUFTable } from "./uf-table";
import { renderDataSection } from "./data-view";

/**
 * Monta uma carga do dashboard dentro do painel atual. É chamado de novo a cada troca de aba,
 * depois que o HTML do painel é restaurado, por isso todos os listeners são religados aqui.
 */
export function initializeDashboard(data: DashboardData, municipalities: AreaCollection, states: AreaCollection): void {
  const state = new DashboardState(data.meta);
  state.groups = enrichGroups(data.g);

  const map = createMap(state, municipalities, states, g => pick(g, false));
  map.place(state.groups);

  const ufSelect = $<HTMLSelectElement>("uf");
  const backButton = $<HTMLButtonElement>("back");

  function render() {
    map.draw();
    renderList(state, g => pick(g, true));
    renderCard(state, clearSelection);
    renderSummary(state);
    renderUFTable(state, setUF);
    renderDataSection(state, g => pick(g, true));
  }

  function clearSelection() {
    state.selected = null;
    map.draw();
    renderCard(state, clearSelection);
  }

  function pick(g: EnrichedGroup, scrollToMap: boolean) {
    state.selected = g;
    map.draw();
    renderCard(state, clearSelection);
    const points = [g.xy, g.xo].filter((p): p is [number, number] => p != null);
    if (points.length) map.zoomToPoints(points);
    if (scrollToMap) $("sec-mapa").scrollIntoView({ behavior: "smooth", block: "start" });
    else if (matchMedia("(hover:none)").matches) $("card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function setUF(uf: string) {
    state.uf = uf;
    ufSelect.value = uf;
    backButton.hidden = !uf;
    state.resetSelection();
    if (uf) {
      map.zoomToFeatures({ type: "FeatureCollection", features: states.features.filter(f => areaCode(f) === CODEOF[uf]) });
    } else {
      map.resetZoom();
    }
    render();
  }

  function applyFilterChange() {
    state.resetSelection();
    render();
  }

  // Estado
  for (const uf of [...new Set(state.groups.map(g => g.uf))].sort()) ufSelect.add(new Option(uf, uf));
  ufSelect.onchange = () => setUF(ufSelect.value);
  backButton.onclick = () => setUF("");

  // Busca de município
  const byLabel = new Map<string, EnrichedGroup>();
  const municipalitiesList = [...new Map(state.groups.map(g => [g.uf + g.ib, g])).values()]
    .sort((a, b) => a.m.localeCompare(b.m));
  const datalist = $<HTMLDataListElement>("muns");
  for (const g of municipalitiesList) {
    const label = `${unescapeHTML(g.m)} (${g.uf})`;
    byLabel.set(label, g);
    datalist.append(new Option(label, label));
  }
  const search = $<HTMLInputElement>("q");
  search.addEventListener("change", () => {
    const g = byLabel.get(search.value);
    if (!g) return;
    state.uf = g.uf;
    ufSelect.value = g.uf;
    backButton.hidden = false;
    state.resetSelection();
    const feature = map.municipalityFeature(g.ib);
    if (feature) map.zoomToFeatures({ type: "FeatureCollection", features: [feature] }, .4);
    render();
    search.blur();
  });

  // Filtro de vencedor
  const winnerChips = document.querySelectorAll<HTMLButtonElement>("[data-win]");
  winnerChips.forEach(chip => {
    chip.onclick = () => {
      state.winner = chip.dataset.win as WinnerFilter;
      winnerChips.forEach(x => x.setAttribute("aria-pressed", String(x === chip)));
      applyFilterChange();
    };
  });

  // Filtros booleanos
  const farChip = $<HTMLButtonElement>("f-far");
  farChip.onclick = () => {
    state.far = !state.far;
    farChip.setAttribute("aria-pressed", String(state.far));
    applyFilterChange();
  };
  const longeChip = $<HTMLButtonElement>("f-longe");
  longeChip.onclick = () => {
    state.longe = !state.longe;
    longeChip.setAttribute("aria-pressed", String(state.longe));
    applyFilterChange();
  };

  $("more").onclick = () => {
    state.shown += 20;
    renderList(state, g => pick(g, true));
  };

  $("gen").textContent = data.meta.gen ?? "";
  $("registry-date").textContent = data.meta.reg ?? "";
  $("source-sections").textContent = int(data.meta.secoes);

  render();
}
