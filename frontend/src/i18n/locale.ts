import { useSyncExternalStore } from "react";

export type Locale = "en" | "de";
const STORAGE_KEY = "dh-compass:language";
const listeners = new Set<() => void>();
function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "en" || saved === "de") return saved;
  } catch {
    /* Storage can be unavailable in private browser sessions. */
  }
  return typeof navigator !== "undefined" && navigator.language.startsWith("de")
    ? "de"
    : "en";
}
let locale: Locale = initialLocale();
export function getLocale(): Locale {
  return locale;
}
export function getFormatLocale(): string {
  return locale === "de" ? "de-DE" : "en-US";
}
export function setLocale(next: Locale): void {
  locale = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* Session-only preference. */
  }
  if (typeof document !== "undefined") document.documentElement.lang = next;
  listeners.forEach((notify) => notify());
}
function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  return () => listeners.delete(notify);
}
/** Subscribe without remounting a page, losing form values or interrupting runs. */
export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, getLocale, () => "en");
}
if (typeof document !== "undefined") document.documentElement.lang = locale;
