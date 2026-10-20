import type { ConfigMetadata, DashboardData, LoadedData } from "../types";

export function prepareDashboardData(rows: Record<string, unknown>[], metadata?: ConfigMetadata): DashboardData;

export function loadDashboardData(
  url: string | URL,
  metadata?: ConfigMetadata,
  d3?: { dsv?: unknown } | undefined,
  format?: "csv" | "json",
): Promise<LoadedData>;
