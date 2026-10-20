import type { Feature, FeatureCollection, Geometry } from "geojson";

/** [secao, eleitores, aptos, abstencao, lula, flavio, outros, brancos, nulos] */
export type SectionRow = [
  number, number,
  number | null, number | null, number | null, number | null,
  number | null, number | null, number | null,
];

export type LatLon = [number, number];

/** Grupo de seções que mudaram do mesmo local original para o mesmo local novo. */
export interface Group {
  uf: string;
  m: string;
  ib: number;
  z: number;
  o: string;
  f: string;
  eo: string;
  ef: string;
  bf: string;
  km: number | null;
  po: LatLon | null;
  pf: LatLon | null;
  longe: boolean | null;
  nv: boolean;
  s: SectionRow[];
}

export interface ConfigMetadata {
  extractionDate?: string;
  gen?: string;
  reg?: string;
  electionDate?: string;
  previousElectionDate?: string;
}

export interface Meta extends ConfigMetadata {
  secoes: number;
  eleitores: number;
  municipios: number;
  aptos: number;
  abst: number;
  lula: number;
  flavio: number;
  outros: number;
  brancos: number;
  nulos: number;
}

export interface DashboardData {
  meta: Meta;
  g: Group[];
}

export interface Snapshot {
  extractedAt: string | null;
  dateLabel?: string;
  data: DashboardData;
}

export interface LoadedData extends DashboardData {
  snapshots: Snapshot[];
}

export interface DashboardConfig {
  dataUrl: string;
  dataFormat?: "csv" | "json";
  municipalitiesUrl: string;
  statesUrl: string;
  metadata?: ConfigMetadata;
}

export interface AreaProperties {
  codarea?: string | number;
  id?: string | number;
}

export type AreaFeature = Feature<Geometry, AreaProperties>;
export type AreaCollection = FeatureCollection<Geometry, AreaProperties>;

export type Winner = "lula" | "flavio" | "empate";
export type WinnerFilter = "all" | "lula" | "flavio";

export interface Totals {
  el: number;
  ap: number;
  ab: number;
  l: number;
  fv: number;
  ot: number;
  b: number;
  n: number;
}

/** Grupo com totais agregados, índice e posição projetada no mapa. */
export interface EnrichedGroup extends Group, Totals {
  i: number;
  v: number;
  lr: number;
  fr: number;
  ar: number;
  xy: [number, number] | null;
  xo: [number, number] | null;
}
