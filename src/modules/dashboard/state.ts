import type { EnrichedGroup, Group, Meta, SectionRow, Totals, Winner, WinnerFilter } from "../../types";

const TOTAL_FIELDS: (keyof Totals)[] = ["el", "ap", "ab", "l", "fv", "ot", "b", "n"];

export function enrichGroups(groups: Group[]): EnrichedGroup[] {
  return groups.map((g, i) => {
    const t: Totals = { el: 0, ap: 0, ab: 0, l: 0, fv: 0, ot: 0, b: 0, n: 0 };
    for (const s of g.s) {
      TOTAL_FIELDS.forEach((field, j) => { t[field] += s[j + 1] || 0; });
    }
    const v = t.l + t.fv + t.ot;
    return {
      ...g, ...t, i, v,
      lr: v ? t.l / v : 0,
      fr: v ? t.fv / v : 0,
      ar: t.ap ? t.ab / t.ap : 0,
      xy: null, xo: null,
    };
  });
}

export const winnerOf = (s: SectionRow): Winner | null =>
  s[4] == null || s[5] == null ? null : s[4] > s[5] ? "lula" : s[5] > s[4] ? "flavio" : "empate";

/** Estado mutável de filtros e seleção, compartilhado por todos os módulos de render de uma carga. */
export class DashboardState {
  groups: EnrichedGroup[] = [];
  far = false;
  longe = false;
  winner: WinnerFilter = "all";
  uf = "";
  selected: EnrichedGroup | null = null;
  shown = 20;

  constructor(public readonly meta: Meta) {}

  sectionOk = (s: SectionRow): boolean => this.winner === "all" || winnerOf(s) === this.winner;

  visible = (g: EnrichedGroup, ignoreUF = false): boolean =>
    (ignoreUF || !this.uf || g.uf === this.uf)
    && g.s.some(this.sectionOk)
    && (!this.far || (g.km != null && g.km >= 2))
    && (!this.longe || g.longe === true);

  visibleGroups = (ignoreUF = false): EnrichedGroup[] => this.groups.filter(g => this.visible(g, ignoreUF));

  colorOf = (g: EnrichedGroup): string => {
    if (!g.v) return "var(--other)";
    if (g.l <= g.fv) return "var(--flavio)";
    const margin = g.lr - g.fr;
    return margin >= .3 ? "var(--l3)" : margin >= .1 ? "var(--l2)" : "var(--l1)";
  };

  scopeLabel = (includeUF = true): string => [
    includeUF && this.uf,
    this.winner === "lula" ? "seções onde Lula venceu" : this.winner === "flavio" ? "seções onde Flávio venceu" : "",
    this.far ? "mudaram 2 km ou mais" : "",
    this.longe ? "região longe da urna" : "",
  ].filter(Boolean).join(" · ");

  resetSelection(): void {
    this.selected = null;
    this.shown = 20;
  }
}
