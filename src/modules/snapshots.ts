import type { AreaCollection, Snapshot } from "../types";
import { $, $maybe } from "../utils/dom";
import { timeLabelOf } from "../utils/format";
import { initializeDashboard } from "./dashboard";
import { groupByDay, latestLoadIndex } from "./snapshot-days";
import { renderTimeline } from "./timeline";

const timeLabel = (snapshot: Snapshot) => snapshot.extractedAt ? timeLabelOf(snapshot.extractedAt) : "Único";

/**
 * Abas de versões diárias + aba "Linha do tempo". Cada ativação restaura o HTML original do painel
 * e monta o dashboard da carga escolhida por cima.
 */
export function initializeSnapshotTabs(snapshots: Snapshot[], municipalities: AreaCollection, states: AreaCollection): void {
  const days = groupByDay(snapshots);
  const tabs = $("snapshot-tabs");
  const panel = $("snapshot-panel");
  const panelTemplate = panel.innerHTML;

  const selectTab = (predicate: (tab: HTMLElement) => boolean) => {
    for (const tab of tabs.querySelectorAll<HTMLElement>('[role="tab"]')) {
      const selected = predicate(tab);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    // O seletor de horário só aparece para o dia ativo; nos demais, confundiria a leitura.
    for (const select of tabs.querySelectorAll<HTMLSelectElement>(".snapshot-load-select")) {
      const ownTab = tabs.querySelector<HTMLElement>(`[role="tab"][data-day="${select.dataset.day}"]`);
      select.hidden = ownTab?.getAttribute("aria-selected") !== "true";
    }
  };

  const activateTimeline = () => {
    selectTab(tab => tab.dataset.timeline === "true");
    panel.innerHTML = panelTemplate;
    panel.setAttribute("aria-labelledby", "snapshot-tab-timeline");

    const wrapper = document.createElement("div");
    wrapper.style.marginTop = "20px";
    const title = document.createElement("h3");
    title.textContent = "Linha do tempo";
    title.style.margin = "0 0 12px 0";
    const subtitle = document.createElement("div");
    subtitle.className = "facts";
    subtitle.style.fontSize = ".82rem";
    subtitle.textContent = "Evolução dos dados ao longo das extrações. Compare como os dados mudaram entre as diferentes cargas do dia.";
    wrapper.append(title, subtitle, $("timeline-charts"));
    panel.appendChild(wrapper);

    renderTimeline(snapshots);
  };

  /** Ativa um dia; sem índice explícito, abre a carga mais recente dele. */
  const activateDay = (dayKey: string, loadIndex?: number) => {
    const day = days.find(d => d.key === dayKey)!;
    const index = loadIndex ?? latestLoadIndex(day);
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

    if (day.loads.length > 1) {
      const select = document.createElement("select");
      select.className = "snapshot-load-select";
      select.dataset.day = day.key;
      select.setAttribute("aria-label", `Cargas para ${day.label}`);
      select.onchange = () => activateDay(day.key, Number(select.value));
      // Prefixo com o dia para o horário nunca parecer pertencer a outra aba.
      const shortDay = day.label.replace(/\/\d{4}$/, "");
      day.loads.forEach((load, loadIndex) => select.append(new Option(`${shortDay} · ${timeLabel(load)}`, String(loadIndex))));
      group.appendChild(select);
    }

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
