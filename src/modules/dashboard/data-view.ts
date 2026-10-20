import type { EnrichedGroup } from "../../types";
import { $maybe, unescapeHTML } from "../../utils/dom";
import { int, kmf } from "../../utils/format";
import type { DashboardState } from "./state";
import { winnerOf } from "./state";

export interface FlatSection {
  uf: string;
  municipio: string;
  cd_ibge: number;
  zona: number;
  secao: number;
  eleitores: number;
  local_1t: string;
  endereco_1t: string;
  lat_1t: number | null;
  lon_1t: number | null;
  local_2t: string;
  endereco_2t: string;
  bairro_2t: string;
  lat_2t: number | null;
  lon_2t: number | null;
  distancia_km: number | null;
  regiao_longe_da_urna: boolean | null;
  aptos_1t: number | null;
  abstencao_1t: number | null;
  lula_1t: number | null;
  flavio_1t: number | null;
  outros_1t: number | null;
  brancos_1t: number | null;
  nulos_1t: number | null;
  vencedor_1t: string;
  group: EnrichedGroup;
}

/** Achata os grupos de seções em uma lista individual de seções alteradas. */
export function flattenSections(groups: EnrichedGroup[]): FlatSection[] {
  const result: FlatSection[] = [];
  for (const g of groups) {
    const mun = unescapeHTML(g.m);
    const loc1 = unescapeHTML(g.o);
    const loc2 = unescapeHTML(g.f);
    const end1 = unescapeHTML(g.eo);
    const end2 = unescapeHTML(g.ef);
    const bai2 = unescapeHTML(g.bf);

    for (const s of g.s) {
      const win = winnerOf(s);
      const winnerLabel = win === "lula" ? "Lula" : win === "flavio" ? "Flávio" : win === "empate" ? "Empate" : "—";
      result.push({
        uf: g.uf,
        municipio: mun,
        cd_ibge: g.ib,
        zona: g.z,
        secao: s[0],
        eleitores: s[1] || 0,
        local_1t: loc1,
        endereco_1t: end1,
        lat_1t: g.po ? g.po[0] : null,
        lon_1t: g.po ? g.po[1] : null,
        local_2t: loc2,
        endereco_2t: end2,
        bairro_2t: bai2,
        lat_2t: g.pf ? g.pf[0] : null,
        lon_2t: g.pf ? g.pf[1] : null,
        distancia_km: g.km,
        regiao_longe_da_urna: g.longe,
        aptos_1t: s[2],
        abstencao_1t: s[3],
        lula_1t: s[4],
        flavio_1t: s[5],
        outros_1t: s[6],
        brancos_1t: s[7],
        nulos_1t: s[8],
        vencedor_1t: winnerLabel,
        group: g,
      });
    }
  }
  return result;
}

/** Escapa campo para CSV (adiciona aspas se contiver ponto-e-vírgula, quebra de linha ou aspas). */
function escapeCSV(val: unknown): string {
  if (val === null || val === undefined) return "";
  const str = String(val);
  if (/[;"\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

/** Gera string CSV com todas as colunas no padrão brasileiro (delimitador ponto-e-vírgula). */
export function generateCSV(sections: FlatSection[]): string {
  const headers = [
    "uf", "municipio", "cd_ibge", "zona", "secao", "eleitores",
    "local_1t", "endereco_1t", "lat_1t", "lon_1t",
    "local_2t", "endereco_2t", "bairro_2t", "lat_2t", "lon_2t",
    "distancia_km", "regiao_longe_da_urna",
    "aptos_1t", "abstencao_1t", "lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t",
    "vencedor_1t",
  ];

  const rows = sections.map(s => [
    s.uf,
    s.municipio,
    s.cd_ibge,
    s.zona,
    s.secao,
    s.eleitores,
    s.local_1t,
    s.endereco_1t,
    s.lat_1t != null ? s.lat_1t.toString().replace(".", ",") : "",
    s.lon_1t != null ? s.lon_1t.toString().replace(".", ",") : "",
    s.local_2t,
    s.endereco_2t,
    s.bairro_2t,
    s.lat_2t != null ? s.lat_2t.toString().replace(".", ",") : "",
    s.lon_2t != null ? s.lon_2t.toString().replace(".", ",") : "",
    s.distancia_km != null ? s.distancia_km.toString().replace(".", ",") : "",
    s.regiao_longe_da_urna === true ? "Sim" : s.regiao_longe_da_urna === false ? "Não" : "",
    s.aptos_1t ?? "",
    s.abstencao_1t ?? "",
    s.lula_1t ?? "",
    s.flavio_1t ?? "",
    s.outros_1t ?? "",
    s.brancos_1t ?? "",
    s.nulos_1t ?? "",
    s.vencedor_1t,
  ].map(escapeCSV).join(";"));

  return [headers.join(";"), ...rows].join("\r\n");
}

/** Dispara o download de um arquivo no navegador do usuário. */
export function triggerDownload(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const PAGE_SIZE = 30;

/** Gerencia a exibição e downloads na seção #sec-dados. */
export function renderDataSection(state: DashboardState, onPickGroup?: (group: EnrichedGroup) => void): void {
  const secDados = $maybe("sec-dados");
  if (!secDados) return;

  const allSections = flattenSections(state.groups);

  // Inicializa botões de download
  const btnCsv = $maybe<HTMLButtonElement>("btn-download-csv");
  if (btnCsv) {
    btnCsv.onclick = () => {
      const csv = generateCSV(allSections);
      // UTF-8 BOM (\uFEFF) para garantir abertura correta de acentos no Excel
      triggerDownload("\uFEFF" + csv, "secoes_eleitorais_alteradas_2t_2026.csv", "text/csv;charset=utf-8;");
    };
  }

  const btnJson = $maybe<HTMLButtonElement>("btn-download-json");
  if (btnJson) {
    btnJson.onclick = () => {
      // Exporta lista limpa de objetos sem referência circular
      const cleanList = allSections.map(({ group, ...rest }) => rest);
      const json = JSON.stringify(cleanList, null, 2);
      triggerDownload(json, "secoes_eleitorais_alteradas_2t_2026.json", "application/json;charset=utf-8;");
    };
  }

  // Preenche select de UFs
  const ufFilter = $maybe<HTMLSelectElement>("data-uf-filter");
  if (ufFilter) {
    const currentVal = ufFilter.value;
    const ufs = [...new Set(allSections.map(s => s.uf))].sort();
    ufFilter.innerHTML = '<option value="">Todos os estados</option>';
    for (const uf of ufs) {
      const opt = document.createElement("option");
      opt.value = uf;
      opt.textContent = uf;
      if (uf === currentVal) opt.selected = true;
      ufFilter.appendChild(opt);
    }
  }

  const searchInput = $maybe<HTMLInputElement>("data-search");
  const counter = $maybe("data-counter");
  const tbody = $maybe<HTMLTableSectionElement>("data-tbody");
  const loadMoreBtn = $maybe<HTMLButtonElement>("data-load-more");

  let currentLimit = PAGE_SIZE;

  function filterSections(): FlatSection[] {
    const query = (searchInput?.value || "").trim().toLowerCase();
    const ufVal = ufFilter?.value || "";

    return allSections.filter(s => {
      if (ufVal && s.uf !== ufVal) return false;
      if (query) {
        const matchMun = s.municipio.toLowerCase().includes(query);
        const matchLoc1 = s.local_1t.toLowerCase().includes(query);
        const matchLoc2 = s.local_2t.toLowerCase().includes(query);
        const matchSec = String(s.secao).includes(query);
        const matchZona = String(s.zona).includes(query);
        const matchUF = s.uf.toLowerCase() === query;
        if (!matchMun && !matchLoc1 && !matchLoc2 && !matchSec && !matchZona && !matchUF) {
          return false;
        }
      }
      return true;
    });
  }

  function updateTable(): void {
    if (!tbody) return;
    const filtered = filterSections();
    const visible = filtered.slice(0, currentLimit);

    if (counter) {
      const totalEleitores = filtered.reduce((acc, s) => acc + s.eleitores, 0);
      counter.textContent = `Exibindo ${visible.length} de ${filtered.length} seções (${int(totalEleitores)} eleitores)`;
    }

    tbody.innerHTML = "";
    if (visible.length === 0) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="9" style="text-align:center;padding:24px;color:var(--muted)">Nenhuma seção encontrada com os filtros selecionados.</td>';
      tbody.appendChild(tr);
    } else {
      for (const s of visible) {
        const tr = document.createElement("tr");
        tr.className = "data-row";
        tr.title = "Clique para localizar no mapa";

        const badgeClass = s.vencedor_1t === "Lula" ? "badge-win-lula" : s.vencedor_1t === "Flávio" ? "badge-win-flavio" : "badge-win-other";

        tr.innerHTML = `
          <td style="text-align:left;font-weight:600">${s.uf}</td>
          <td style="text-align:left">${s.municipio}</td>
          <td style="text-align:center">${s.zona}</td>
          <td style="text-align:center;font-weight:600">${s.secao}</td>
          <td style="text-align:right">${int(s.eleitores)}</td>
          <td style="text-align:left;max-width:200px" title="${s.local_1t}">${s.local_1t}</td>
          <td style="text-align:left;max-width:200px;font-weight:500" title="${s.local_2t}">${s.local_2t}</td>
          <td style="text-align:right">${s.distancia_km != null ? kmf(s.distancia_km) : "—"}</td>
          <td style="text-align:center"><span class="${badgeClass}">${s.vencedor_1t}</span></td>
        `;

        if (onPickGroup) {
          tr.style.cursor = "pointer";
          tr.onclick = () => onPickGroup(s.group);
        }

        tbody.appendChild(tr);
      }
    }

    if (loadMoreBtn) {
      loadMoreBtn.hidden = currentLimit >= filtered.length;
      loadMoreBtn.textContent = `Mostrar mais (${filtered.length - currentLimit} restantes)`;
    }
  }

  if (searchInput) {
    searchInput.oninput = () => {
      currentLimit = PAGE_SIZE;
      updateTable();
    };
  }

  if (ufFilter) {
    ufFilter.onchange = () => {
      currentLimit = PAGE_SIZE;
      updateTable();
    };
  }

  if (loadMoreBtn) {
    loadMoreBtn.onclick = () => {
      currentLimit += 50;
      updateTable();
    };
  }

  updateTable();
}
