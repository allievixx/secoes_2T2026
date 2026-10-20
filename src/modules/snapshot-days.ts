import type { Snapshot } from "../types.ts";
import { dayKeyOf, dayLabelOf } from "../utils/format.ts";

export interface Day {
  key: string;
  label: string;
  loads: Snapshot[];
}

/** Agrupa extrações por dia (fuso de Brasília), do mais antigo para o mais recente; idem para as cargas de cada dia. */
export function groupByDay(snapshots: Snapshot[]): Day[] {
  const byDay = new Map<string, Day>();
  for (const snapshot of snapshots) {
    const key = snapshot.extractedAt ? dayKeyOf(snapshot.extractedAt) : snapshot.dateLabel ?? "Carga atual";
    const label = snapshot.extractedAt ? dayLabelOf(snapshot.extractedAt) : snapshot.dateLabel ?? "Carga atual";
    if (!byDay.has(key)) byDay.set(key, { key, label, loads: [] });
    byDay.get(key)!.loads.push(snapshot);
  }
  const days = [...byDay.values()].sort((a, b) => a.key.localeCompare(b.key));
  for (const day of days) day.loads.sort((a, b) => (a.extractedAt ?? "").localeCompare(b.extractedAt ?? ""));
  return days;
}

/** Carga mais recente de um dia (a última, dada a ordenação crescente). */
export const latestLoadIndex = (day: Day): number => day.loads.length - 1;
