import { $ } from "../../utils/dom";
import { int, pct1 } from "../../utils/format";
import { winnerOf, type DashboardState } from "./state";

interface UFRow {
  uf: string; n: number; el: number; mun: Set<string>; mv: number;
  wl: number; wf: number; we: number; l: number; f: number; o: number;
  ap: number; ab: number; far: number; lon: number; lonUnknown: number;
}

const HEADERS = ["UF", "Seções", "Eleitores", "Municípios", "Mudanças de local", "Lula venceu", "Flávio venceu", "Empate",
  "Lula %", "Flávio %", "Abstenção", "Mudou 2 km+", "Região longe"];

const makeRow = (uf: string): UFRow => ({
  uf, n: 0, el: 0, mun: new Set(), mv: 0, wl: 0, wf: 0, we: 0, l: 0, f: 0, o: 0, ap: 0, ab: 0, far: 0, lon: 0, lonUnknown: 0,
});

/** Tabela por estado: segue todos os filtros, exceto o de UF, para permitir comparar estados. */
export function renderUFTable(state: DashboardState, onSelectUF: (uf: string) => void): void {
  const by: Record<string, UFRow> = {};
  const total = makeRow("Total");
  for (const g of state.visibleGroups(true)) {
    const r = by[g.uf] ??= makeRow(g.uf);
    for (const s of g.s.filter(state.sectionOk)) {
      for (const x of [r, total]) {
        x.n++; x.el += s[1]; x.l += s[4] || 0; x.f += s[5] || 0; x.o += s[6] || 0; x.ap += s[2] || 0; x.ab += s[3] || 0;
        const w = winnerOf(s);
        if (w === "lula") x.wl++; else if (w === "flavio") x.wf++; else if (w === "empate") x.we++;
        if (g.km != null && g.km >= 2) x.far++;
        if (g.longe) x.lon++;
        if (g.longe == null) x.lonUnknown++;
        x.mun.add(g.uf + g.ib);
      }
    }
    r.mv++; total.mv++;
  }

  const rows = Object.values(by).sort((a, b) => b.n - a.n);
  const cells = (r: UFRow) => {
    const V = r.l + r.f + r.o;
    return [
      r.uf, int(r.n), int(r.el), int(r.mun.size), int(r.mv), int(r.wl), int(r.wf), int(r.we),
      V ? pct1(r.l / V) : "–", V ? pct1(r.f / V) : "–", r.ap ? pct1(r.ab / r.ap) : "–",
      int(r.far), r.lonUnknown ? "–" : int(r.lon),
    ].map(v => `<td>${v}</td>`).join("");
  };

  const scope = state.scopeLabel(false);
  $("ufscope").textContent = `${rows.length} estado${rows.length !== 1 ? "s" : ""}${scope ? " · " + scope : ""}`;
  $("uftab").innerHTML =
    `<thead><tr>${HEADERS.map(v => `<th>${v}</th>`).join("")}</tr></thead>`
    + `<tbody>${rows.map(r => `<tr data-uf="${r.uf}" class="${state.uf === r.uf ? "on" : ""}">${cells(r)}</tr>`).join("")}</tbody>`
    + `<tfoot><tr>${cells(total)}</tr></tfoot>`;

  document.querySelectorAll<HTMLTableRowElement>("#uftab tbody tr").forEach(tr => {
    tr.onclick = () => {
      const uf = tr.dataset.uf ?? "";
      onSelectUF(state.uf === uf ? "" : uf);
      $("top").scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
}
