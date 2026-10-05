import { german } from "./de";
import { getLocale } from "./locale";

const patterns = Object.entries(german)
  .filter(([key]) => /\{(?:\d+|\w+)\}/.test(key))
  .map(([key, translated]) => ({
    regex: new RegExp(
      "^" +
        key
          .split(/(\{\w+\})/)
          .map((part) =>
            /^\{\w+\}$/.test(part)
              ? "([\\s\\S]+?)"
              : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
          )
          .join("") +
        "$",
    ),
    placeholders: key.match(/\{\w+\}/g) ?? [],
    translated,
  }));

export function tr(message: string): string;
export function tr<T>(message: T): T;
/** Translate presentation text only; identifiers, files and user input stay intact. */
export function tr<T>(message: T): T | string {
  if (getLocale() === "en" || typeof message !== "string") return message;
  const text = message.trim();
  let translated = german[text];
  if (!translated) {
    for (const pattern of patterns) {
      const match = pattern.regex.exec(text);
      if (!match) continue;
      translated = pattern.placeholders.reduce(
        (result, token, index) =>
          result.replaceAll(token, tr(match[index + 1])),
        pattern.translated,
      );
      break;
    }
  }
  return translated ? message.replace(text, translated) : message;
}
