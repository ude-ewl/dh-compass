import type { ConfigurationField } from "../../api/projects";

export type ConfigurationDocument = Record<string, unknown>;

export function cloneConfiguration<T>(value: T): T {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

/** Read a flattened TOML path from a JSON configuration document. */
export function getConfigurationValue(
  document: ConfigurationDocument,
  path: string,
): unknown {
  let current: unknown = document;
  for (const segment of path.split(".")) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

/** Return a detached document with one flattened TOML path replaced. */
export function setConfigurationValue(
  document: ConfigurationDocument,
  path: string,
  value: unknown,
): ConfigurationDocument {
  const result = cloneConfiguration(document);
  const segments = path.split(".");
  let current: Record<string, unknown> = result;
  segments.forEach((segment, index) => {
    if (index === segments.length - 1) {
      current[segment] = value;
      return;
    }
    const next = current[segment];
    if (!next || typeof next !== "object" || Array.isArray(next)) {
      current[segment] = {};
    }
    current = current[segment] as Record<string, unknown>;
  });
  return result;
}

export function deleteConfigurationValue(
  document: ConfigurationDocument,
  path: string,
): ConfigurationDocument {
  const result = cloneConfiguration(document);
  const segments = path.split(".");
  const containers: Record<string, unknown>[] = [result];
  let current: Record<string, unknown> = result;
  for (const segment of segments.slice(0, -1)) {
    const next = current[segment];
    if (!next || typeof next !== "object" || Array.isArray(next)) return result;
    current = next as Record<string, unknown>;
    containers.push(current);
  }
  delete current[segments[segments.length - 1]];
  for (let index = containers.length - 1; index > 0; index -= 1) {
    if (Object.keys(containers[index]).length > 0) break;
    delete containers[index - 1][segments[index - 1]];
  }
  return result;
}

/** Reset a configured leaf to its default, or remove an added map member. */
export function resetConfigurationValue(
  document: ConfigurationDocument,
  path: string,
  defaultValue: unknown,
  hasDefault: boolean,
): ConfigurationDocument {
  return hasDefault
    ? setConfigurationValue(document, path, defaultValue)
    : deleteConfigurationValue(document, path);
}

export function configurationValuesEqual(
  left: unknown,
  right: unknown,
): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function tomlKey(value: string): string {
  return /^[A-Za-z0-9_-]+$/.test(value) ? value : JSON.stringify(value);
}

function tomlScalar(value: unknown): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number")
    return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return `[${value.map((item) => tomlScalar(item)).join(", ")}]`;
  }
  throw new Error(`Unsupported TOML value: ${typeof value}`);
}

/** Serialize the effective document for the raw-TOML editor. */
export function serializeConfigurationToml(
  document: ConfigurationDocument,
): string {
  const lines: string[] = [];
  const writeTable = (table: Record<string, unknown>, path: string[]) => {
    if (path.length > 0) lines.push(`[${path.map(tomlKey).join(".")}]`);
    Object.entries(table).forEach(([key, value]) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) {
        lines.push(`${tomlKey(key)} = ${tomlScalar(value)}`);
      }
    });
    Object.entries(table).forEach(([key, value]) => {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        if (lines.length > 0) lines.push("");
        writeTable(value as Record<string, unknown>, [...path, key]);
      }
    });
  };
  writeTable(document, []);
  return `${lines.join("\n")}\n`;
}

export function fieldValue(
  field: ConfigurationField,
  document: ConfigurationDocument,
): unknown {
  const value = getConfigurationValue(document, field.key);
  return value === undefined ? field.value : value;
}

export function fieldMatchesSearch(
  field: ConfigurationField,
  search: string,
): boolean {
  if (!search.trim()) return true;
  const needle = search.trim().toLocaleLowerCase();
  return [field.key, field.label, field.description, field.group_label ?? ""]
    .join(" ")
    .toLocaleLowerCase()
    .includes(needle);
}

export function coerceFieldInput(
  field: ConfigurationField,
  input: string,
): unknown {
  if (field.data_type === "number") {
    const value = Number(input);
    return input === "" ? "" : Number.isFinite(value) ? value : input;
  }
  if (field.data_type === "integer") {
    const value = Number(input);
    return input === "" ? "" : Number.isInteger(value) ? value : input;
  }
  if (field.data_type === "array" || field.data_type === "object") {
    try {
      return JSON.parse(input) as unknown;
    } catch {
      return input;
    }
  }
  return input;
}

export function displayValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined) return "—";
  return JSON.stringify(value);
}

export function impactLabel(field: ConfigurationField): string {
  if (field.impact === "preview") return "Requires new preview";
  if (field.impact === "run") return "Requires new run";
  return "No downstream run impact";
}

export function fieldErrorFor(
  errors: Array<{ path: string; message: string }>,
  path: string,
): string | undefined {
  const direct = errors.find((error) => error.path === path);
  if (direct) return direct.message;
  return errors.find(
    (error) =>
      error.path.startsWith(`${path}.`) || path.startsWith(`${error.path}.`),
  )?.message;
}

export function sectionFields(
  fields: ConfigurationField[],
): Map<string, ConfigurationField[]> {
  const sections = new Map<string, ConfigurationField[]>();
  fields.forEach((field) => {
    const key = field.group ?? field.section;
    const values = sections.get(key) ?? [];
    values.push(field);
    sections.set(key, values);
  });
  return sections;
}

export function isCostCurveField(field: ConfigurationField): boolean {
  return (
    field.key.startsWith("economics.cost_structures.") ||
    field.key.startsWith("economics.fixed_cost_structures.") ||
    field.key.startsWith("economics.variable_om_cost_structures.") ||
    field.key.startsWith("network.transfer_station_cost_structure.") ||
    field.key.startsWith("network.pump_cost_structure.")
  );
}

export function isTechnologyMapField(field: ConfigurationField): boolean {
  const parts = field.key.split(".");
  return (
    parts[0] === "technologies" && parts.length >= 4 && parts[1] !== "pv_module"
  );
}

export function costCurveKey(field: ConfigurationField): string {
  return field.key.split(".").slice(0, -1).join(".");
}

export function technologyMapKey(field: ConfigurationField): string {
  return field.key.split(".")[1];
}
