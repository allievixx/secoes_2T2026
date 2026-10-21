import type { AreaCollection, Snapshot } from "../types";
import { $, $maybe } from "../utils/dom";
import { timeLabelOf } from "../utils/format";
import { initializeDashboard } from "./dashboard";
import { groupByDay, latestLoadIndex } from "./snapshot-days";
import { renderDedicatedTimelineView, renderTimeline } from "./timeline";

const timeLabel = (snapshot: Snapshot) => snapshot.extractedAt ? timeLabelOf(snapshot.extractedAt, true) : "Horário indisponível";

/**
 * Abas de versões diárias + aba "Linha do tempo". Cada ativação restaura o HTML original do painel
 * e monta o dashboard da carga escolhida por cima.
 */
export function initializeSnapshotTabs(snapshots: Snapshot[], municipalities: AreaCollection, states: AreaCollection): void {
  const days = groupByDay(snapshots);
  const tabs = $("snapshot-tabs");
  const panel = $("snapshot-panel");
  const panelTemplate = panel.innerHTML;
  const selectedLoads = new Map(days.map(day => [day.key, latestLoadIndex(day)]));

  const selectTab = (predicate: (tab: HTMLElement) => boolean) => {
    for (const tab of tabs.querySelectorAll<HTMLElement>('[role="tab"]')) {
      const selected = predicate(tab);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
  };

  const activateTimeline = () => {
    selectTab(tab => tab.dataset.timeline === "true");
    panel.setAttribute("aria-labelledby", "snapshot-tab-timeline");
    renderDedicatedTimelineView(panel, snapshots, () => {
      activateDay(days[days.length - 1].key);
    });
  };

  /** Ativa um dia preservando a extração escolhida; inicialmente, usa a mais recente. */
  const activateDay = (dayKey: string, loadIndex?: number) => {
    const day = days.find(d => d.key === dayKey)!;
    const index = loadIndex ?? selectedLoads.get(dayKey) ?? latestLoadIndex(day);
    selectedLoads.set(dayKey, index);
    const snapshot = day.loads[index];
    selectTab(tab => tab.dataset.day === dayKey);

    const select = tabs.querySelector<HTMLSelectElement>(`select[data-day="${dayKey}"]`);
    if (select) select.value = String(index);

    panel.innerHTML = panelTemplate;
    panel.setAttribute("aria-labelledby", `snapshot-tab-${dayKey}`);

    const extractionDate = day.loads.length > 1 ? `${day.label} - ${timeLabel(snapshot)}` : day.label;
    const gen = snapshot.extractedAt ? `${day.label} às ${timeLabel(snapshot)}` : snapshot.data.meta.gen;
    initializeDashboard({
      ...snapshot.data,
      meta: { ...snapshot.data.meta, extractionDate, gen },
    }, municipalities, states);

    renderTimeline(snapshots);
  };

  const focusDay = (index: number) => {
    activateDay(days[index].key);
    $maybe(`snapshot-tab-${days[index].key}`)?.focus();
  };

  days.forEach((day, index) => {
    const group = document.createElement("div");
    group.className = "snapshot-day";

    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "snapshot-tab";
    tab.id = `snapshot-tab-${day.key}`;
    tab.dataset.day = day.key;
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", "snapshot-panel");
    tab.setAttribute("aria-selected", "false");
    tab.tabIndex = -1;
    tab.textContent = day.label;
    tab.onclick = () => activateDay(day.key);
    tab.onkeydown = event => {
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % days.length;
      else if (event.key === "ArrowLeft") next = (index - 1 + days.length) % days.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = days.length - 1;
      else return;
      event.preventDefault();
      focusDay(next);
    };
    group.appendChild(tab);

    const label = document.createElement("label");
    label.className = "snapshot-load-label";
    label.textContent = "Extração (Brasília)";
    const select = document.createElement("select");
    select.className = "snapshot-load-select";
    select.dataset.day = day.key;
    select.setAttribute("aria-label", `Extração de ${day.label} (horário de Brasília)`);
    select.setAttribute("aria-controls", "snapshot-panel");
    select.onchange = () => activateDay(day.key, Number(select.value));
    day.loads.forEach((load, loadIndex) => {
      const latest = loadIndex === latestLoadIndex(day) ? " · mais recente" : "";
      select.append(new Option(`${timeLabel(load)}${latest}`, String(loadIndex)));
    });
    select.value = String(latestLoadIndex(day));
    label.appendChild(select);
    group.appendChild(label);

    tabs.append(group);
  });

  const timelineTab = $maybe<HTMLButtonElement>("snapshot-tab-timeline");
  if (timelineTab) {
    timelineTab.onclick = activateTimeline;
    timelineTab.onkeydown = event => {
      if (event.key === "ArrowRight" || event.key === "Home") focusDay(0);
      else if (event.key === "ArrowLeft") focusDay(days.length - 1);
      else if (event.key === "End") { activateTimeline(); timelineTab.focus(); }
      else return;
      event.preventDefault();
    };
  }

  // Abre no dia mais recente, na carga mais recente.
  activateDay(days[days.length - 1].key);
}
