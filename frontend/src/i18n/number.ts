import { getFormatLocale } from "./locale";

/** Keep locale-specific decimals, with a narrow space between digit groups. */
export function formatNumericValue(
  value: number,
  options: Intl.NumberFormatOptions = {},
): string {
  return new Intl.NumberFormat(getFormatLocale(), options)
    .formatToParts(value)
    .map((part) => (part.type === "group" ? "\u202f" : part.value))
    .join("");
}
