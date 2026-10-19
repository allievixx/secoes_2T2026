const REQUIRED_COLUMNS = [
  "uf", "municipio", "cd_ibge", "zona", "secao", "eleitores",
  "local_1t", "endereco_1t", "lat_1t", "lon_1t",
  "local_2t", "endereco_2t", "bairro_2t", "lat_2t", "lon_2t",
  "distancia_km", "regiao_longe_da_urna", "entrou_desde_15_10",
  "aptos_1t", "abstencao_1t", "lula_1t", "flavio_1t", "outros_1t",
  "brancos_1t", "nulos_1t",
];

function number(value, column, row, required = false) {
  const text = String(value ?? "").trim();
  if (!text && !required) return null;
  const result = text ? Number(text.replace(",", ".")) : NaN;
  if (!Number.isFinite(result)) {
    throw new Error(`Valor inválido em ${column}, linha ${row + 2}.`);
  }
  return result;
}

function boolean(value, column, row, nullable = false) {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text && nullable) return null;
  if (["true", "1", "sim"].includes(text)) return true;
  if (["false", "0", "não", "nao", ""].includes(text)) return false;
  throw new Error(`Valor inválido em ${column}, linha ${row + 2}.`);
}

function coordinates(row, suffix, index) {
  const lat = number(row[`lat_${suffix}`], `lat_${suffix}`, index);
  const lon = number(row[`lon_${suffix}`], `lon_${suffix}`, index);
  if (lat === null || lon === null) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    throw new Error(`Coordenadas inválidas na linha ${index + 2}.`);
  }
  return [lat, lon];
}

// Strings são usadas nos templates HTML da visualização existente.
const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);

export function prepareDashboardData(rows, metadata = {}) {
  const columns = rows.columns ?? Object.keys(rows[0] ?? {});
  const missing = REQUIRED_COLUMNS.filter(column => !columns.includes(column));
  if (missing.length) throw new Error(`Colunas ausentes na fonte: ${missing.join(", ")}.`);
  if (!rows.length) throw new Error("A fonte de dados não contém seções.");

  const groups = new Map();
  const sections = new Set();
  const municipalities = new Set();
  const meta = {
    ...metadata, secoes: 0, eleitores: 0, municipios: 0, novas: 0, novas_el: 0,
    aptos: 0, abst: 0, lula: 0, flavio: 0, outros: 0, brancos: 0, nulos: 0,
  };

  rows.forEach((row, index) => {
    const uf = String(row.uf ?? "").trim().toUpperCase();
    if (!/^(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)$/.test(uf)) {
      throw new Error(`UF inválida na linha ${index + 2}.`);
    }
    const ib = number(row.cd_ibge, "cd_ibge", index, true);
    const z = number(row.zona, "zona", index, true);
    const section = number(row.secao, "secao", index, true);
    const id = JSON.stringify([uf, ib, z, section]);
    if (sections.has(id)) throw new Error(`Seção duplicada na linha ${index + 2}.`);
    sections.add(id);
    const g = {
      uf, m: escapeHTML(row.municipio), ib, z,
      o: escapeHTML(row.local_1t), f: escapeHTML(row.local_2t),
      eo: escapeHTML(row.endereco_1t), ef: escapeHTML(row.endereco_2t),
      bf: escapeHTML(row.bairro_2t),
      km: number(row.distancia_km, "distancia_km", index),
      po: coordinates(row, "1t", index), pf: coordinates(row, "2t", index),
      longe: boolean(row.regiao_longe_da_urna, "regiao_longe_da_urna", index, true),
    };
    if (g.km !== null && g.km < 0) throw new Error(`Distância inválida na linha ${index + 2}.`);
    const nv = boolean(row.entrou_desde_15_10, "entrou_desde_15_10", index, true);
    const values = ["eleitores", "aptos_1t", "abstencao_1t", "lula_1t", "flavio_1t", "outros_1t", "brancos_1t", "nulos_1t"]
      .map(column => {
        const value = number(row[column], column, index, column === "eleitores");
        if (value !== null && (!Number.isInteger(value) || value < 0)) {
          throw new Error(`Contagem inválida em ${column}, linha ${index + 2}.`);
        }
        return value;
      });
    const key = JSON.stringify(g);
    if (!groups.has(key)) groups.set(key, { ...g, nv: false, s: [] });
    const group = groups.get(key);
    group.s.push([section, ...values, nv]);
    group.nv ||= nv;
    meta.secoes++;
    const totals = ["eleitores", "aptos", "abst", "lula", "flavio", "outros", "brancos", "nulos"];
    totals.forEach((field, i) => { meta[field] += values[i] ?? 0; });
    if (nv) { meta.novas++; meta.novas_el += values[0]; }
    municipalities.add(`${uf}:${ib}`);
  });
  meta.municipios = municipalities.size;
  return { meta, g: [...groups.values()] };
}

export async function loadDashboardData(url, metadata = {}, d3 = globalThis.d3, format = "csv") {
  if (!["csv", "json"].includes(format)) throw new Error("Formato de dados não suportado.");
  if (format === "csv" && !d3?.dsv) throw new Error("Não foi possível carregar a biblioteca D3. Verifique a conexão.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    let rows;
    if (format === "json") {
      const response = await fetch(url, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(`Não foi possível consultar a API de dados (HTTP ${response.status}).`);
      const payload = await response.json();
      rows = Array.isArray(payload) ? payload : payload?.rows;
      if (!Array.isArray(rows)) throw new Error("A API deve retornar uma lista de seções ou um objeto com rows.");
    } else {
      rows = await d3.dsv(";", url, { cache: "no-store", signal: controller.signal });
    }
    return prepareDashboardData(rows, metadata);
  } finally {
    clearTimeout(timeout);
  }
}