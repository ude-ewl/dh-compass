import { getFormatLocale } from "../../i18n/locale";
import { formatNumericValue } from "../../i18n/number";
export function formatNumber(value: unknown, digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return formatNumericValue(value, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

export function formatEuro(value: unknown, digits = 0): string {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted} €/a`;
}

export function formatEuroCapital(value: unknown, digits = 0): string {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted} €`;
}

export function formatEuroPerMwh(value: unknown, digits = 1): string {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted} €/MWh`;
}

export function formatMwh(value: unknown, digits = 1): string {
  const formatted = formatNumber(value, digits);
  return formatted === "—" ? formatted : `${formatted} MWh/a`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(getFormatLocale(), {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    timeZoneName: "short",
    year: "numeric",
  }).format(date);
}

export function formatFileSize(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
