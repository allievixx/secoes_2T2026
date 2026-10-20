import * as d3 from "d3";
import type { AreaCollection, AreaFeature, EnrichedGroup } from "../../types";
import { $ } from "../../utils/dom";
import { int, kmf, pct, walk } from "../../utils/format";
import type { DashboardState } from "./state";

const W = 1000, H = 1000;
type Point = [number, number];
type Ring = number[][];

export const areaCode = (f: AreaFeature): string => String(f.properties.codarea ?? f.properties.id);

/** Corrige anéis com orientação invertida, que o D3 interpreta como "o mundo inteiro menos o polígono". */
function fixPolygon(rings: Ring[]): Ring[] {
  const area = d3.geoArea({ type: "Polygon", coordinates: rings as [number, number][][] });
  return area > 2 * Math.PI ? rings.map(r => r.slice().reverse()) : rings;
}

function normalizeWinding(collections: AreaCollection[]): void {
  for (const collection of collections) {
    for (const f of collection.features) {
      const g = f.geometry;
      if (g?.type === "Polygon") g.coordinates = fixPolygon(g.coordinates as Ring[]) as typeof g.coordinates;
      else if (g?.type === "MultiPolygon") g.coordinates = g.coordinates.map(p => fixPolygon(p as Ring[])) as typeof g.coordinates;
    }
  }
}

export interface MapController {
  /** Posiciona cada grupo no mapa (xy = local novo, xo = local antigo quando houve deslocamento). */
  place(groups: EnrichedGroup[]): void;
  draw(): void;
  zoomToFeatures(fc: AreaCollection, pad?: number): void;
  zoomToPoints(points: Point[]): void;
  resetZoom(): void;
  municipalityFeature(ibge: number): AreaFeature | undefined;
}

export function createMap(
  state: DashboardState,
  municipalities: AreaCollection,
  states: AreaCollection,
  onPick: (g: EnrichedGroup) => void,
): MapController {
  normalizeWinding([municipalities, states]);

  const svg = d3.select<SVGSVGElement, unknown>("#map").attr("viewBox", `0 0 ${W} ${H}`);
  const projection = d3.geoMercator().fitExtent([[10, 10], [W - 10, H - 10]], municipalities);
  const path = d3.geoPath(projection);
  const withChanges = new Set(state.groups.map(g => String(g.ib)));

  const gMap = svg.append("g"), gLines = svg.append("g"), gPoints = svg.append("g");
  gMap.selectAll("path.m").data(municipalities.features).join("path")
    .attr("class", d => "m" + (withChanges.has(areaCode(d)) ? " has" : "")).attr("d", path);
  gMap.selectAll("path.uf").data(states.features).join("path").attr("class", "uf").attr("d", path);

  let k = 1;
  const rPoint = (g: EnrichedGroup) => Math.max(1.8, Math.sqrt(g.el) / 8) / Math.pow(k, .75) * 1.4;
  const rOrigin = () => 2 / Math.pow(k, .75) * 1.4;

  const tip = $("tip"), box = $("sec-mapa");
  function showTip(e: MouseEvent, html: string) {
    const r = box.getBoundingClientRect();
    tip.innerHTML = html;
    tip.hidden = false;
    let x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
    if (x + tip.offsetWidth > r.width - 8) x = e.clientX - r.left - tip.offsetWidth - 14;
    if (y + tip.offsetHeight > r.height - 8) y = e.clientY - r.top - tip.offsetHeight - 14;
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  }

  const tipHTML = (g: EnrichedGroup) =>
    `<b>${g.m}</b> · ${g.uf} · zona ${g.z}<br>${g.o} → <b>${g.f}</b><br>`
    + `${g.km != null ? `${kmf(g.km)} (${walk(g.km)})` : "distância desconhecida"} · ${g.s.length} seções, ${int(g.el)} eleitores<br>`
    + `1º turno: Lula ${pct(g.lr)} · Flávio ${pct(g.fr)} · abstenção ${pct(g.ar)}`;

  const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([1, 300])
    .filter(e => e.type === "touchstart" ? e.touches.length > 1 : !e.button)
    .on("zoom", e => {
      for (const layer of [gMap, gLines, gPoints]) layer.attr("transform", e.transform);
      k = e.transform.k;
      gPoints.selectAll<SVGCircleElement, EnrichedGroup>("circle").attr("r", rPoint);
      gLines.selectAll("circle").attr("r", rOrigin);
    });
  svg.call(zoom).on("dblclick.zoom", null).style("touch-action", "pan-y");
  $("zin").onclick = () => svg.transition().duration(300).call(zoom.scaleBy, 1.8);
  $("zout").onclick = () => svg.transition().duration(300).call(zoom.scaleBy, 1 / 1.8);

  const zoomToBox = (x0: number, y0: number, x1: number, y1: number, k: number) =>
    svg.transition().duration(600).call(
      zoom.transform,
      d3.zoomIdentity.translate(W / 2, H / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2),
    );

  const project = (latLon: [number, number]): Point | null => projection([latLon[1], latLon[0]]) as Point | null;

  return {
    place(groups) {
      for (const g of groups) {
        g.xy = g.pf ? project(g.pf) : g.po ? project(g.po) : null;
        g.xo = g.po && g.pf && g.km != null && g.km > .05 ? project(g.po) : null;
      }
    },

    draw() {
      const vis = state.visibleGroups().filter(g => g.xy).sort((a, b) => b.el - a.el);
      const moved = vis.filter(g => g.xo);
      tip.hidden = true;
      gLines.selectAll<SVGLineElement, EnrichedGroup>("line").data(moved, g => g.i).join("line").attr("class", "mv")
        .attr("x1", g => g.xo![0]).attr("y1", g => g.xo![1]).attr("x2", g => g.xy![0]).attr("y2", g => g.xy![1]);
      gLines.selectAll<SVGCircleElement, EnrichedGroup>("circle").data(moved, g => g.i).join("circle").attr("class", "o")
        .attr("cx", g => g.xo![0]).attr("cy", g => g.xo![1]).attr("r", rOrigin);
      gPoints.selectAll<SVGCircleElement, EnrichedGroup>("circle").data(vis, g => g.i).join("circle")
        .attr("class", g => "p" + (state.selected === g ? " on" : ""))
        .attr("cx", g => g.xy![0]).attr("cy", g => g.xy![1]).attr("r", rPoint).attr("fill", state.colorOf)
        .on("mousemove", (e: MouseEvent, g) => showTip(e, tipHTML(g)))
        .on("mouseleave", () => { tip.hidden = true; })
        .on("click", (_e, g) => onPick(g));
    },

    zoomToFeatures(fc, pad = .85) {
      const [[x0, y0], [x1, y1]] = path.bounds(fc);
      const k = Math.min(300, pad / Math.max((x1 - x0) / W, (y1 - y0) / H, 1e-6));
      zoomToBox(x0, y0, x1, y1, k);
    },

    zoomToPoints(points) {
      const xs = points.map(p => p[0]), ys = points.map(p => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const k = Math.min(40, .6 / Math.max((x1 - x0) / W, (y1 - y0) / H, .004));
      zoomToBox(x0, y0, x1, y1, k);
    },

    resetZoom() {
      svg.transition().duration(600).call(zoom.transform, d3.zoomIdentity);
    },

    municipalityFeature(ibge) {
      return municipalities.features.find(f => areaCode(f) === String(ibge));
    },
  };
}
