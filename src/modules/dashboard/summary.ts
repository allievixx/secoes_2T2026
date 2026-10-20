import { $ } from "../../utils/dom";
import { int, pct1 } from "../../utils/format";
import type { DashboardState } from "./state";

export function renderSummary(state: DashboardState): void {
  const { meta } = state;
  const T = { n: 0, el: 0, ap: 0, ab: 0, l: 0, f: 0, o: 0, bn: 0, far: 0, lon: 0, lonUnknown: 0, mun: new Set<string>() };
  for (const g of state.visibleGroups()) {
    for (const s of g.s.filter(state.sectionOk)) {
      T.n++; T.el += s[1]; T.ap += s[2] || 0; T.ab += s[3] || 0;
      T.l += s[4] || 0; T.f += s[5] || 0; T.o += s[6] || 0; T.bn += (s[7] || 0) + (s[8] || 0);
      if (g.km != null && g.km >= 2) T.far++;
      if (g.longe) T.lon++;
      if (g.longe == null) T.lonUnknown++;
      T.mun.add(g.uf + g.ib);
    }
  }
  const V = T.l + T.f + T.o;
  const scope = state.scopeLabel();

  $("scope").textContent = `2º turno · ${meta.electionDate}${scope ? " · " + scope : ""}`;
  $("headline").textContent = `${int(T.n)} seç${T.n !== 1 ? "ões vão" : "ão vai"} votar em outro lugar no 2º turno`;

  // Metadados de configuração entram como texto, não como HTML.
  const lede = $("lede");
  lede.replaceChildren();
  const pieces: (string | [string])[] = [
    "São ", [int(T.el) + " eleitores"],
    ` em ${int(T.mun.size)} município${T.mun.size !== 1 ? "s" : ""} que vão votar em `, ["outro local"],
    ` no dia ${meta.electionDate}. Quem for ao mesmo lugar de ${meta.previousElectionDate} pode não encontrar a sua seção. `
    + `Lista de seções alteradas no 2º turno publicada pelo TSE em ${meta.gen}.`,
  ];
  for (const piece of pieces) {
    if (Array.isArray(piece)) {
      const b = document.createElement("b");
      b.textContent = piece[0];
      lede.append(b);
    } else {
      lede.append(piece);
    }
  }

  const kpis: [string, string, string][] = [
    ["hot", int(T.n), "seções mudam de local"],
    ["hot", int(T.el), "eleitores nelas"],
    ["", V ? pct1(T.l / V) : "–", "Lula nelas no 1º turno"],
    ["", int(T.far), "seções mudaram 2 km ou mais"],
    ...(T.lonUnknown ? [] : [["", int(T.lon), "seções em região longe da urna"] as [string, string, string]]),
    ["", int(T.mun.size), "municípios"],
    ["", T.ap ? pct1(T.ab / T.ap) : "–", "abstenção no 1º turno (Brasil: 20,8%)"],
  ];
  $("kpis").innerHTML = kpis
    .map(([c, v, l]) => `<div class="kpi ${c}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

  const parts: [string, number, string][] = [
    ["Lula", T.l, "var(--l3)"], ["Flávio", T.f, "var(--flavio)"], ["Outros", T.o, "var(--other)"],
    ["Brancos e nulos", T.bn, "var(--bn)"], ["Abstenção", T.ab, "var(--off)"],
  ];
  const total = parts.reduce((sum, p) => sum + p[1], 0) || 1;
  $("stack").innerHTML = parts
    .map(p => `<i style="width:${p[1] / total * 100}%;background:${p[2]}" title="${p[0]}"></i>`).join("");
  $("keys").innerHTML = parts
    .map(p => `<span><i class="sw" style="background:${p[2]};border:1px solid var(--line)"></i>${p[0]} <b>${pct1(p[1] / total)}</b></span>`).join("")
    + `<span>dos ${int(T.ap)} aptos</span>`;
}
