import test from "node:test";
import assert from "node:assert/strict";
import { groupByDay, latestLoadIndex } from "../src/modules/snapshot-days.ts";

const snap = (extractedAt, dateLabel) => ({ extractedAt, dateLabel, data: { meta: {}, g: [] } });

test("agrupa snapshots por dia no fuso de Brasília, do mais antigo para o mais recente", () => {
  const days = groupByDay([
    snap("2026-10-20T09:00:00Z"),
    snap("2026-10-19T10:00:00Z"),
    snap("2026-10-19T14:00:00Z"),
  ]);
  assert.deepEqual(days.map(d => d.key), ["2026-10-19", "2026-10-20"]);
  assert.deepEqual(days.map(d => d.label), ["19/10/2026", "20/10/2026"]);
  assert.deepEqual(days.map(d => d.loads.length), [2, 1]);
});

test("ordena as cargas de um dia da mais antiga para a mais recente", () => {
  const [day] = groupByDay([
    snap("2026-10-19T14:00:00Z"),
    snap("2026-10-19T10:00:00Z"),
    snap("2026-10-19T12:00:00Z"),
  ]);
  assert.deepEqual(day.loads.map(l => l.extractedAt), [
    "2026-10-19T10:00:00Z", "2026-10-19T12:00:00Z", "2026-10-19T14:00:00Z",
  ]);
  assert.equal(day.loads[latestLoadIndex(day)].extractedAt, "2026-10-19T14:00:00Z");
});

test("usa a data local: 02:00 UTC ainda é o dia anterior em Brasília", () => {
  const days = groupByDay([snap("2026-10-20T02:00:00Z"), snap("2026-10-20T12:00:00Z")]);
  assert.deepEqual(days.map(d => d.key), ["2026-10-19", "2026-10-20"]);
});

test("suporta snapshot sem extractedAt (carga atual)", () => {
  const days = groupByDay([snap(null, "Carga atual"), snap("2026-10-19T14:00:00Z")]);
  assert.equal(days.length, 2);
  assert.ok(days.some(d => d.label === "Carga atual" && d.loads.length === 1));
});
