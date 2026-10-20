import type { EnrichedGroup } from "../../types";
import { $ } from "../../utils/dom";
import { kmf, pct, walk } from "../../utils/format";
import type { DashboardState } from "./state";

function rowHTML(state: DashboardState, g: EnrichedGroup): string {
  const winnerNote = state.winner !== "all"
    ? ` (${g.s.filter(state.sectionOk).length} com vitória ${state.winner === "lula" ? "do Lula" : "do Flávio"})`
    : "";
  return `<button type="button" class="row" data-i="${g.i}">`
    + `<span class="nm">${g.m} · ${g.uf} <span style="font-weight:400;color:var(--muted)">zona ${g.z}</span></span>`
    + `<span class="sub">${g.o} → ${g.f}<br>${g.s.length} seç${g.s.length > 1 ? "ões" : "ão"}${winnerNote}`
    + ` · Lula ${pct(g.lr)} · Flávio ${pct(g.fr)} · abstenção ${pct(g.ar)}</span>`
    + `<span class="pc">${g.km != null ? walk(g.km) : "–"}<small>${g.km != null ? kmf(g.km) : "distância ?"}</small></span>`
    + `</button>`;
}

/** Lista paginada de mudanças, da maior distância para a menor; sem distância conhecida ficam por último. */
export function renderList(state: DashboardState, onPick: (g: EnrichedGroup) => void): void {
  const arr = state.visibleGroups().sort((a, b) => (b.km ?? -1) - (a.km ?? -1) || b.el - a.el);
  $("listscope").textContent = (state.uf || "Brasil") + " · maior distância primeiro";
  $("list").innerHTML = arr.length
    ? arr.slice(0, state.shown).map(g => rowHTML(state, g)).join("")
    : '<div class="empty">Nenhuma mudança com esse filtro.</div>';
  $("more").hidden = arr.length <= state.shown;
  $("list").querySelectorAll<HTMLButtonElement>("[data-i]").forEach(b => {
    b.onclick = () => onPick(state.groups[Number(b.dataset.i)]);
  });
}
