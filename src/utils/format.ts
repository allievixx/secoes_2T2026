export const int = (value: number | null | undefined): string =>
  value == null ? "–" : value.toLocaleString("pt-BR");

export const pct = (value: number): string => Math.round(value * 100) + "%";

export const pct1 = (value: number): string =>
  (value * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + "%";

export const kmf = (value: number): string =>
  value.toLocaleString("pt-BR", { maximumFractionDigits: value < 10 ? 1 : 0 }) + " km";

/** Tempo de caminhada a 5 km/h, arredondado para múltiplos de 5 minutos. */
export const walk = (km: number): string => {
  const minutes = Math.round(km / 5 * 60 / 5) * 5;
  if (minutes < 60) return `${Math.max(5, minutes)} min a pé`;
  const rest = minutes % 60;
  return `${Math.floor(minutes / 60)}h${rest ? String(rest).padStart(2, "0") : ""} a pé`;
};

const TZ = "America/Sao_Paulo";

export const dayKeyOf = (iso: string): string => {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: TZ,
  }).formatToParts(new Date(iso));
  const part = (type: string) => parts.find(item => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
};

export const dayLabelOf = (iso: string): string =>
  new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeZone: TZ }).format(new Date(iso));

export const timeLabelOf = (iso: string): string =>
  new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: TZ }).format(new Date(iso));
