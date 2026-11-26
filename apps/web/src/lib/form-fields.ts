/** The eight field types of a request form, as the API stores them. */

export const FIELD_TYPES = [
  "text",
  "number",
  "date",
  "select",
  "employee",
  "file",
  "boolean",
  "reference",
] as const;
export type FieldType = (typeof FIELD_TYPES)[number];

export type FormField = {
  key: string;
  type: FieldType;
  label: string;
  required: boolean;
  help: string;
  multiline?: boolean;
  max_length?: number;
  integer?: boolean;
  min?: number | null;
  max?: number | null;
  currency?: string | null;
  with_time?: boolean;
  multiple?: boolean;
  options?: string[];
};

/** A new field with the settings of its type and a key no other field uses. */
export function newField(type: FieldType, existing: readonly FormField[]): FormField {
  const used = new Set(existing.map((field) => field.key));
  let index = existing.length + 1;
  while (used.has(`field_${index}`)) {
    index += 1;
  }
  return { ...settingsOf(type), key: `field_${index}`, type, label: "", required: false, help: "" };
}

function settingsOf(type: FieldType): Partial<FormField> {
  switch (type) {
    case "text":
      return { multiline: false };
    case "number":
      return { integer: false, min: null, max: null, currency: null };
    case "date":
      return { with_time: false };
    case "select":
      return { multiple: false, options: [] };
    default:
      return {};
  }
}

/** Changing the type keeps what every field has and resets what only the old type had. */
export function withType(field: FormField, type: FieldType): FormField {
  const { key, label, required, help } = field;
  return { ...settingsOf(type), key, type, label, required, help };
}

/** What is sent to the API: only the settings of the field's own type. */
export function toPayload(field: FormField): Record<string, unknown> {
  const base = {
    key: field.key,
    type: field.type,
    label: field.label,
    required: field.required,
    help: field.help,
  };
  switch (field.type) {
    case "text":
      // The length limit is left to the server's default for the chosen kind.
      return { ...base, multiline: field.multiline ?? false };
    case "number":
      return {
        ...base,
        integer: field.integer ?? false,
        min: field.min ?? null,
        max: field.max ?? null,
        currency: field.currency ? field.currency.toUpperCase() : null,
      };
    case "date":
      return { ...base, with_time: field.with_time ?? false };
    case "select":
      return { ...base, multiple: field.multiple ?? false, options: field.options ?? [] };
    default:
      return base;
  }
}

export function linesOf(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

export function toNumberOrNull(raw: string): number | null {
  const text = raw.trim().replace(",", ".");
  if (text === "") {
    return null;
  }
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}
