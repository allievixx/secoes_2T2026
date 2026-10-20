import * as d3 from "d3";
import { loadDashboardData } from "./data/dashboard-data.js";
import { initializeNavigation } from "./modules/navigation";
import { initializeSnapshotTabs } from "./modules/snapshots";
import type { AreaCollection, DashboardConfig } from "./types";
import { $ } from "./utils/dom";
import { fetchJSON } from "./utils/http";

function assertGeoJSON(geo: unknown, label: string): asserts geo is AreaCollection {
  const fc = geo as Partial<AreaCollection> | null;
  if (fc?.type !== "FeatureCollection" || !fc.features?.length) {
    throw new Error(`A fonte do mapa (${label}) não retornou uma coleção de geometrias válida.`);
  }
}

async function start(): Promise<void> {
  try {
    if (location.protocol === "file:") {
      throw new Error("Abra a aplicação por um servidor HTTP ou pelo GitHub Pages. Consulte o README do projeto.");
    }
    const configMeta = document.querySelector<HTMLMetaElement>('meta[name="dashboard-config"]');
    if (!configMeta) throw new Error("Meta tag dashboard-config ausente no HTML.");
    const configURL = new URL(configMeta.content, location.href);
    const config = await fetchJSON<DashboardConfig>(configURL, true);

    const [data, municipalities, states] = await Promise.all([
      loadDashboardData(new URL(config.dataUrl, configURL), config.metadata, d3, config.dataFormat ?? "csv"),
      fetchJSON(new URL(config.municipalitiesUrl, configURL)),
      fetchJSON(new URL(config.statesUrl, configURL)),
    ]);
    assertGeoJSON(municipalities, "municípios");
    assertGeoJSON(states, "estados");

    $("dashboard").hidden = false;
    initializeNavigation();
    initializeSnapshotTabs(data.snapshots, municipalities, states);

    $("dashboard").setAttribute("aria-busy", "false");
    $("load-status").hidden = true;
  } catch (error) {
    $("dashboard").hidden = true;
    $("load-title").textContent = "Não foi possível carregar o dashboard";
    $("load-message").textContent = error instanceof DOMException && error.name === "AbortError"
      ? "A fonte demorou mais de 30 segundos para responder. Tente novamente."
      : error instanceof Error ? error.message : String(error);
    $("retry-load").hidden = false;
  }
}

$("retry-load").onclick = () => location.reload();
start();
