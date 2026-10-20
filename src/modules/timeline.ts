import * as d3 from "d3";
import type { Snapshot } from "../types";
import { $maybe } from "../utils/dom";
import { dayLabelOf, timeLabelOf } from "../utils/format";

interface TimelinePoint {
  time: string;
  sections: number;
  voters: number;
  eligible: number;
}

type MetricKey = Exclude<keyof TimelinePoint, "time">;

const METRICS: { key: MetricKey; label: string; color: string }[] = [
  { key: "sections", label: "Seções que mudam de local", color: "var(--l3)" },
  { key: "voters", label: "Eleitores nelas", color: "var(--accent)" },
  { key: "eligible", label: "Aptos", color: "var(--muted)" },
];

const VIEW_W = 700, VIEW_H = 300;
const MARGIN = { top: 20, right: 30, bottom: 30, left: 70 };

const formatAxisNumber = (value: d3.NumberValue) => Number(value).toLocaleString("pt-BR");

/** Rótulo "dd/mm hh:mm" no fuso de Brasília, para distinguir cargas de dias diferentes. */
function pointLabel(snapshot: Snapshot): string {
  if (!snapshot.extractedAt) return "Único";
  return `${dayLabelOf(snapshot.extractedAt).replace(/\/\d{4}$/, "")} ${timeLabelOf(snapshot.extractedAt)}`;
}

function summarize(snapshot: Snapshot): TimelinePoint {
  const point: TimelinePoint = {
    time: pointLabel(snapshot),
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
  const title = document.createElement("div");
  title.className = "timeline-title";
  title.textContent = metric.label;
  chart.appendChild(title);

  const width = VIEW_W - MARGIN.left - MARGIN.right;
  const height = VIEW_H - MARGIN.top - MARGIN.bottom;
  const x = d3.scaleLinear().domain([0, data.length - 1]).range([0, width]);
  const y = d3.scaleLinear().domain([0, d3.max(data, d => d[metric.key]) ?? 0]).range([height, 0]);
  const line = d3.line<TimelinePoint>().x((_d, i) => x(i)).y(d => y(d[metric.key]));

  const svg = d3.create("svg").attr("viewBox", [0, 0, VIEW_W, VIEW_H]).attr("class", "timeline-svg");
  const g = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

  g.append("g").attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x).tickValues(d3.range(data.length)).tickFormat(d => data[Number(d)]?.time ?? ""))
    .style("font-size", "12px");
  g.append("g").call(d3.axisLeft(y).tickFormat(formatAxisNumber)).style("font-size", "12px");

  g.append("path").datum(data)
    .attr("fill", "none").attr("stroke", metric.color).attr("stroke-width", 2.5).attr("d", line);

  g.selectAll(".dot").data(data).enter().append("circle")
    .attr("cx", (_d, i) => x(i)).attr("cy", d => y(d[metric.key]))
    .attr("r", 4).attr("fill", metric.color).attr("opacity", 0.7);

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
