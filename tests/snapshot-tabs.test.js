import test from "node:test";
import assert from "node:assert/strict";

// Simulates the grouping logic for days and loads
function groupSnapshotsByDay(snapshots) {
  const dayKey = snapshot => {
    if (!snapshot.extractedAt) return snapshot.dateLabel;
    const parts = new Intl.DateTimeFormat("en-CA", {
      year:"numeric", month:"2-digit", day:"2-digit", timeZone:"America/Sao_Paulo",
    }).formatToParts(new Date(snapshot.extractedAt));
    const part = type => parts.find(item => item.type === type).value;
    return `${part("year")}-${part("month")}-${part("day")}`;
  };
  
  const timeLabel = snapshot => snapshot.extractedAt
    ? new Intl.DateTimeFormat("pt-BR", { hour:"2-digit", minute:"2-digit", timeZone:"America/Sao_Paulo" }).format(new Date(snapshot.extractedAt))
    : "Único";
  
  const byDay = new Map();
  for (const snapshot of snapshots) {
    const key = dayKey(snapshot);
    if (!byDay.has(key)) {
      const parts = new Intl.DateTimeFormat("en-CA", {
        year:"numeric", month:"2-digit", day:"2-digit", timeZone:"America/Sao_Paulo",
      }).formatToParts(new Date(snapshot.extractedAt || new Date()));
      const part = type => parts.find(item => item.type === type).value;
      const label = snapshot.extractedAt
        ? new Intl.DateTimeFormat("pt-BR", { dateStyle:"short", timeZone:"America/Sao_Paulo" }).format(new Date(snapshot.extractedAt))
        : snapshot.dateLabel;
      byDay.set(key, { key, label, loads:[] });
    }
    byDay.get(key).loads.push(snapshot);
  }
  
  const days = [...byDay.values()].sort((a,b) => b.key.localeCompare(a.key));
  days.forEach(day => {
    day.loads.sort((a,b) => (b.extractedAt || "").localeCompare(a.extractedAt || ""));
  });
  
  return days;
}

test("agrupa snapshots por dia", () => {
  const snapshots = [
    { extractedAt: "2026-10-19T10:00:00Z", data: {} },
    { extractedAt: "2026-10-19T14:00:00Z", data: {} },
    { extractedAt: "2026-10-20T09:00:00Z", data: {} },
  ];
  
  const days = groupSnapshotsByDay(snapshots);
  assert.equal(days.length, 2);
  assert.equal(days[0].loads.length, 1);
  assert.equal(days[1].loads.length, 2);
});

test("mantém ordem de cargas por data de extração", () => {
  const snapshots = [
    { extractedAt: "2026-10-19T10:00:00Z", data: {} },
    { extractedAt: "2026-10-19T14:00:00Z", data: {} },
    { extractedAt: "2026-10-19T12:00:00Z", data: {} },
  ];
  
  const days = groupSnapshotsByDay(snapshots);
  assert.equal(days.length, 1);
  assert.equal(days[0].loads.length, 3);
  assert.equal(days[0].loads[0].extractedAt, "2026-10-19T14:00:00Z");
  assert.equal(days[0].loads[1].extractedAt, "2026-10-19T12:00:00Z");
  assert.equal(days[0].loads[2].extractedAt, "2026-10-19T10:00:00Z");
});

test("suporta snapshot sem extractedAt (carga atual)", () => {
  const snapshots = [
    { extractedAt: null, dateLabel: "Carga atual", data: {} },
    { extractedAt: "2026-10-19T14:00:00Z", data: {} },
  ];
  
  const days = groupSnapshotsByDay(snapshots);
  assert.equal(days.length, 2);
  assert.equal(days[0].label, "Carga atual");
});
