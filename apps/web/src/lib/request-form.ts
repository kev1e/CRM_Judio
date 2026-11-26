/** Filling in a request form: what the browser keeps and what it sends.
 *  The server alone decides what a valid value is. */
import { type FormField } from "@/lib/form-fields";
import { fromLocalInput } from "@/lib/tasks";

export type FormValue = string | string[] | File | null;
export type FormValues = Record<string, FormValue>;

export function emptyValues(fields: readonly FormField[]): FormValues {
  const values: FormValues = {};
  for (const field of fields) {
    values[field.key] =
      field.type === "select" && field.multiple ? [] : field.type === "file" ? null : "";
  }
  return values;
}

/** The JSON values and the files of a submission. Empty answers are left out. */
export function toSubmission(
  fields: readonly FormField[],
  values: FormValues,
): { values: Record<string, unknown>; files: Map<string, File> } {
  const result: Record<string, unknown> = {};
  const files = new Map<string, File>();
  for (const field of fields) {
    const value = values[field.key];
    if (value instanceof File) {
      files.set(field.key, value);
    } else if (Array.isArray(value)) {
      if (value.length > 0) {
        result[field.key] = value;
      }
    } else if (typeof value === "string" && value.trim() !== "") {
      if (field.type === "boolean") {
        result[field.key] = value === "true";
      } else if (field.type === "date" && field.with_time) {
        result[field.key] = fromLocalInput(value);
      } else {
        result[field.key] = value;
      }
    }
  }
  return { values: result, files };
}

export const REFUSAL_REASONS = [
  "required",
  "invalid",
  "too_long",
  "out_of_range",
  "too_precise",
  "not_integer",
  "not_an_option",
  "unknown_field",
] as const;
export type RefusalReason = (typeof REFUSAL_REASONS)[number];

export function toReason(raw: string | undefined): RefusalReason {
  return (REFUSAL_REASONS as readonly string[]).includes(raw ?? "")
    ? (raw as RefusalReason)
    : "invalid";
}
