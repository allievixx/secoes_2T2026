import * as d3 from "d3";
import type { Snapshot } from "../types";
import { $maybe } from "../utils/dom";
import { dayLabelOf, int, timeLabelOf } from "../utils/format";

export interface TimelinePoint {
  time: string;
  fullDate: string;
  sections: number;
  voters: number;
  eligible: number;
}

type MetricKey = Exclude<keyof TimelinePoint, "time" | "fullDate">;

const METRICS: { key: MetricKey; label: string; color: string }[] = [
  { key: "sections", label: "Seções que mudam de local", color: "var(--l3)" },
  { key: "voters", label: "Eleitores impactados nelas", color: "var(--accent)" },
  { key: "eligible", label: "Eleitores aptos", color: "var(--muted)" },
];

const VIEW_W = 750, VIEW_H = 300;
const MARGIN = { top: 20, right: 30, bottom: 45, left: 75 };

const formatAxisNumber = (value: d3.NumberValue) => Number(value).toLocaleString("pt-BR");

/** Rótulo "dd/mm hh:mm" no fuso de Brasília, para distinguir cargas de dias diferentes. */
function pointLabel(snapshot: Snapshot): string {
  if (!snapshot.extractedAt) return "Único";
  return `${dayLabelOf(snapshot.extractedAt).replace(/\/\d{4}$/, "")} ${timeLabelOf(snapshot.extractedAt)}`;
}

function fullDateLabel(snapshot: Snapshot): string {
  if (!snapshot.extractedAt) return "Carga atual";
  return `${dayLabelOf(snapshot.extractedAt)} às ${timeLabelOf(snapshot.extractedAt)}`;
}

export function summarize(snapshot: Snapshot): TimelinePoint {
  const point: TimelinePoint = {
    time: pointLabel(snapshot),
    fullDate: fullDateLabel(snapshot),
    sections: 0, voters: 0, eligible: 0,
  };
  for (const g of snapshot.data.g) {
    for (const s of g.s) {
      point.sections++;
      point.voters += s[1] || 0;
      point.eligible += s[2] || 0;
    }
  }
  return point;
}

function buildChart(data: TimelinePoint[], metric: typeof METRICS[number]): HTMLElement {
  const chart = document.createElement("div");
  chart.className = "timeline-chart";

  const header = document.createElement("div");
  header.style.display = "flex";
  header.style.justifyContent = "space-between";
  header.style.alignItems = "baseline";
  header.style.marginBottom = "10px";

  const title = document.createElement("div");
  title.className = "timeline-title";
  title.style.margin = "0";
  title.textContent = metric.label;

  const latestVal = data[data.length - 1][metric.key];
  const badge = document.createElement("span");
  badge.style.fontFamily = "var(--f-num)";
  badge.style.fontWeight = "600";
  badge.style.fontSize = "0.95rem";
  badge.style.color = metric.color;
  badge.textContent = `Atual: ${formatAxisNumber(latestVal)}`;

  header.append(title, badge);
  chart.appendChild(header);

  const width = VIEW_W - MARGIN.left - MARGIN.right;
  const height = VIEW_H - MARGIN.top - MARGIN.bottom;
  const x = d3.scaleLinear().domain([0, data.length - 1]).range([0, width]);
  const yMax = d3.max(data, d => d[metric.key]) ?? 0;
  const y = d3.scaleLinear().domain([0, yMax ? yMax * 1.08 : 10]).range([height, 0]);
  const line = d3.line<TimelinePoint>().x((_d, i) => x(i)).y(d => y(d[metric.key]));

  const svg = d3.create("svg").attr("viewBox", [0, 0, VIEW_W, VIEW_H]).attr("class", "timeline-svg");
  const g = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

  // Linhas de grade suaves horizontais
  g.append("g")
    .call(d3.axisLeft(y).ticks(5).tickSize(-width).tickFormat(() => ""))
    .call(grid => grid.select(".domain").remove())
    .call(grid => grid.selectAll(".tick line").attr("stroke", "var(--line)").attr("stroke-opacity", 0.5));

  // Eixo X inclinado para não sobrepor datas
  const xAxis = g.append("g").attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x).tickValues(d3.range(data.length)).tickFormat(d => data[Number(d)]?.time ?? ""))
    .style("font-size", "11px");

  xAxis.selectAll("text")
    .style("text-anchor", "end")
    .attr("dx", "-.5em")
    .attr("dy", ".15em")
    .attr("transform", "rotate(-25)");

  // Eixo Y
  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(formatAxisNumber)).style("font-size", "11px");

  // Linha da série
  g.append("path").datum(data)
    .attr("fill", "none").attr("stroke", metric.color).attr("stroke-width", 2.5).attr("d", line);

  // Pontos
  const dots = g.selectAll(".dot").data(data).enter().append("circle")
    .attr("cx", (_d, i) => x(i)).attr("cy", d => y(d[metric.key]))
    .attr("r", 5).attr("fill", metric.color).attr("stroke", "var(--surface)").attr("stroke-width", 1.5)
    .style("cursor", "pointer");

  dots.append("title")
    .text(d => `${d.fullDate}: ${Number(d[metric.key]).toLocaleString("pt-BR")}`);

  chart.appendChild(svg.node()!);
  return chart;
}

/** Evolução de seções, eleitores e aptos ao longo das extrações. */
export function renderTimeline(snapshots: Snapshot[]): void {
  const container = $maybe("timeline-charts");
  if (!container) return;

  if (snapshots.length < 2) {
    container.innerHTML = '<div class="facts" style="color:var(--muted);padding:12px">Necessário mínimo 2 cargas para comparação temporal.</div>';
    return;
  }

  const data = snapshots.map(summarize);
  container.replaceChildren(...METRICS.map(metric => buildChart(data, metric)));
}

/**
 * Renderiza o painel completo da Linha do Tempo dedicada, sem mapas vazios ou elementos quebrados do dia.
 */
export function renderDedicatedTimelineView(
  panel: HTMLElement,
  snapshots: Snapshot[],
  onBackToLatest?: () => void
): void {
  const data = snapshots.map(summarize);
  const latest = data[data.length - 1];
  const first = data[0];
  const diffSections = latest.sections - first.sections;
  const diffLabel = diffSections !== 0
    ? `${diffSections > 0 ? "+" : ""}${diffSections} (${((diffSections / first.sections) * 100).toFixed(1).replace(".", ",")}%)`
    : "estável";

  panel.innerHTML = `
    <section class="card" id="sec-timeline">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
        <div>
          <div class="eyebrow">Série Histórica Oficial</div>
          <h2 style="font-size:1.35rem">Linha do tempo das extrações</h2>
        </div>
        ${onBackToLatest ? `<button type="button" class="btn-download btn-secondary" id="btn-back-latest">← Voltar ao mapa do dia</button>` : ""}
      </div>
      <p class="lead">Evolução do quantitativo de seções alteradas, eleitores impactados e aptos ao longo de todas as <b>${data.length} extrações</b> do TSE cadastradas.</p>

      <div class="kpis">
        <div class="kpi">
          <div class="v">${data.length}</div>
          <div class="l">Cargas registradas</div>
        </div>
        <div class="kpi hot">
          <div class="v">${int(latest.sections)}</div>
          <div class="l">Seções na carga atual <small style="display:block;font-size:.75rem;color:var(--muted)">variação: ${diffLabel}</small></div>
        </div>
        <div class="kpi">
          <div class="v">${int(latest.voters)}</div>
          <div class="l">Eleitores impactados</div>
        </div>
        <div class="kpi">
          <div class="v">${int(latest.eligible)}</div>
          <div class="l">Eleitores aptos</div>
        </div>
      </div>

      <div id="timeline-charts"></div>

      <div style="margin-top:24px">
        <div class="eyebrow">Detalhamento histórico</div>
        <h3 style="margin:4px 0 12px 0;font-size:1.1rem">Comparativo de todas as cargas do TSE</h3>
        <div class="tblw">
          <table class="timeline-table">
            <thead>
              <tr>
                <th style="text-align:center">Carga</th>
                <th style="text-align:left">Data e Hora (Brasília)</th>
                <th style="text-align:right">Seções</th>
                <th style="text-align:right">Eleitores</th>
                <th style="text-align:right">Aptos</th>
                <th style="text-align:right">Variação Seções</th>
              </tr>
            </thead>
            <tbody id="timeline-tbody"></tbody>
          </table>
        </div>
      </div>
    </section>
  `;

  // Preenche tabela comparativa
  const tbody = panel.querySelector<HTMLTableSectionElement>("#timeline-tbody");
  if (tbody) {
    data.forEach((p, idx) => {
      const prev = idx > 0 ? data[idx - 1] : null;
      const stepDiff = prev ? p.sections - prev.sections : 0;
      const isLatest = idx === data.length - 1;
      const tr = document.createElement("tr");
      if (isLatest) tr.style.fontWeight = "600";

      const diffText = prev
        ? (stepDiff !== 0 ? `${stepDiff > 0 ? "+" : ""}${stepDiff}` : "0")
        : "—";

      tr.innerHTML = `
        <td style="text-align:center">${idx + 1}${isLatest ? ' <span class="tag">Atual</span>' : ""}</td>
        <td style="text-align:left">${p.fullDate}</td>
        <td style="text-align:right">${int(p.sections)}</td>
        <td style="text-align:right">${int(p.voters)}</td>
        <td style="text-align:right">${int(p.eligible)}</td>
        <td style="text-align:right;color:${stepDiff < 0 ? "var(--accent)" : stepDiff > 0 ? "var(--fg)" : "var(--muted)"}">${diffText}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // Renderiza gráficos
  renderTimeline(snapshots);

  // Liga botão de volta se fornecido
  if (onBackToLatest) {
    panel.querySelector<HTMLButtonElement>("#btn-back-latest")?.addEventListener("click", onBackToLatest);
  }
}
