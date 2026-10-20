import type { SectionRow } from "../../types";
import { $ } from "../../utils/dom";
import { int, kmf, pct, pct1, walk } from "../../utils/format";
import { winnerOf, type DashboardState } from "./state";

const WINNER_LABEL = { lula: "Lula", flavio: "Flávio", empate: "Empate" } as const;

function sectionRow(s: SectionRow): string {
  const v = (s[4] || 0) + (s[5] || 0) + (s[6] || 0);
  const w = winnerOf(s);
  const share = (count: number | null, base: number | null) =>
    count != null ? `${int(count)} <small>${base ? pct(count / base) : ""}</small>` : "–";
  return `<tr><td>${s[0]}</td>`
    + `<td style="font-family:var(--f-ui);color:${w === "lula" ? "var(--accent)" : "var(--muted)"}">${w ? WINNER_LABEL[w] : "–"}</td>`
    + `<td>${int(s[1])}</td><td>${share(s[4], v)}</td><td>${share(s[5], v)}</td><td>${int(s[6])}</td>`
    + `<td>${s[7] != null && s[8] != null ? int(s[7] + s[8]) : "–"}</td><td>${share(s[3], s[2])}</td></tr>`;
}

/** Card abaixo do mapa: resumo do recorte atual ou detalhe do grupo selecionado. */
export function renderCard(state: DashboardState, onClear: () => void): void {
  const card = $("card");
  const g = state.selected;

  if (!g) {
    const vis = state.visibleGroups();
    const t = { n: 0, el: 0 };
    for (const grp of vis) for (const s of grp.s.filter(state.sectionOk)) { t.n++; t.el += s[1]; }
    card.innerHTML =
      `<div class="eyebrow">${state.uf || "Brasil"}${state.scopeLabel() ? " · com filtro" : ""}</div>`
      + `<h2>${int(t.n)} seç${t.n !== 1 ? "ões" : "ão"} em ${int(vis.length)} mudança${vis.length !== 1 ? "s" : ""} de local</h2>`
      + `<div class="facts">${int(t.el)} eleitores. Toque num ponto do mapa ou numa linha da lista para ver de onde para onde a seção foi e como ela votou no 1º turno.</div>`;
    return;
  }

  const stack: [number, string][] = [
    [g.l, "var(--l3)"], [g.fv, "var(--flavio)"], [g.ot, "var(--other)"], [g.b + g.n, "var(--bn)"], [g.ab, "var(--off)"],
  ];
  const regiao = g.longe == null ? "sem informação" : g.longe ? "longe" : "perto";

  card.innerHTML = `<div><div class="eyebrow">${g.uf} · ${g.m} · zona ${g.z}</div><h2>${g.f}</h2></div>
    <span class="badge now">Muda de local no 2º turno</span>
    <div class="move">
      <span class="k">1º turno</span><div>${g.o}${g.eo ? `<div class="addr">${g.eo}</div>` : ""}</div>
      <span class="k">2º turno</span><div><b>${g.f}</b>${g.ef ? `<div class="addr">${g.ef}${g.bf ? ` · ${g.bf}` : ""}</div>` : ""}</div>
    </div>
    <div class="facts">
      <span>Distância <b>${g.km != null ? kmf(g.km) : "–"}</b></span>
      ${g.km != null ? `<span>A pé <b>${walk(g.km)}</b></span>` : ""}
      <span>Seções <b>${g.s.length}</b></span>
      <span>Eleitores <b>${int(g.el)}</b></span>
      <span>Região <b style="color:${g.longe ? "var(--accent)" : "inherit"}">${regiao}</b>${g.longe == null ? "" : " da urna"}</span>
    </div>
    <div>
      <div class="eyebrow" style="margin-bottom:6px">1º turno nessas seções</div>
      <div class="stack">${stack.map(([v, c]) => `<i style="width:${g.ap ? v / g.ap * 100 : 0}%;background:${c}"></i>`).join("")}</div>
      <div class="keys" style="margin-top:6px">
        <span>Lula <b>${int(g.l)}</b> (${pct1(g.lr)})</span><span>Flávio <b>${int(g.fv)}</b> (${pct1(g.fr)})</span>
        <span>Outros <b>${int(g.ot)}</b></span><span>Brancos e nulos <b>${int(g.b + g.n)}</b></span>
        <span>Abstenção <b>${int(g.ab)}</b> (${pct1(g.ar)})</span>
      </div>
    </div>
    <div class="tblw"><table>
      <thead><tr><th>Seção</th><th>Venceu</th><th>Eleitores</th><th>Lula</th><th>Flávio</th><th>Outros</th><th>Br/Nulos</th><th>Abst.</th></tr></thead>
      <tbody>${g.s.map(sectionRow).join("")}</tbody>
    </table></div>
    <button type="button" class="more" id="clear">Ver todas as mudanças</button>`;

  $("clear").onclick = onClear;
}
