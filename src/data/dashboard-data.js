const REQUIRED_COLUMNS = [
  "uf", "municipio", "cd_ibge", "zona", "secao", "eleitores",
  "local_1t", "endereco_1t", "lat_1t", "lon_1t",
  "local_2t", "endereco_2t", "bairro_2t", "lat_2t", "lon_2t",
  "distancia_km", "regiao_longe_da_urna",
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
    ...metadata, secoes: 0, eleitores: 0, municipios: 0,
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
    group.s.push([section, ...values]);
    meta.secoes++;
    const totals = ["eleitores", "aptos", "abst", "lula", "flavio", "outros", "brancos", "nulos"];
    totals.forEach((field, i) => { meta[field] += values[i] ?? 0; });
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
    let snapshots;
    if (format === "json") {
      // no-store evita o cache do navegador, mas não invalida respostas já guardadas no CDN do Storage.
      let requestURL = url;
      if (/^https?:\/\//i.test(String(url))) {
        requestURL = new URL(String(url));
        requestURL.searchParams.set("_refresh", String(Date.now()));
      }
      const response = await fetch(requestURL, { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error(`Não foi possível consultar a API de dados (HTTP ${response.status}).`);
      const payload = await response.json();
      if (Array.isArray(payload?.snapshots)) {
        if (!payload.snapshots.length) throw new Error("O histórico não contém extrações.");
        snapshots = payload.snapshots.map((snapshot, index) => {
          const extractedAt = snapshot?.extracted_at;
          const timestamp = typeof extractedAt === "string" ? new Date(extractedAt) : null;
          if (!Array.isArray(snapshot?.rows) || Number.isNaN(timestamp?.getTime())
            || typeof extractedAt !== "string" || !/[zZ]|[+-]\d{2}:\d{2}$/.test(extractedAt)) {
            throw new Error(`Extração inválida no histórico, item ${index + 1}.`);
          }
          return { extractedAt: timestamp.toISOString(), data: prepareDashboardData(snapshot.rows, metadata) };
        }).sort((a,b) => a.extractedAt.localeCompare(b.extractedAt));
      } else {
        rows = Array.isArray(payload) ? payload : payload?.rows;
        if (!Array.isArray(rows)) throw new Error("A API deve retornar uma lista de seções, rows ou snapshots.");
      }
    } else {
      rows = await d3.dsv(";", url, { cache: "no-store", signal: controller.signal });
    }
    if (!snapshots) {
      const data = prepareDashboardData(rows, metadata);
      snapshots = [{ extractedAt: null, dateLabel: metadata.extractionDate || metadata.gen || "Carga atual", data }];
    }
    return { ...snapshots[snapshots.length - 1].data, snapshots };
  } finally {
    clearTimeout(timeout);
  }
}