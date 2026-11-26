import { describe, expect, it } from "vitest";

import {
  FIELD_TYPES,
  type FormField,
  linesOf,
  newField,
  toNumberOrNull,
  toPayload,
  withType,
} from "./form-fields";

describe("form fields", () => {
  it("knows the eight types", () => {
    expect(FIELD_TYPES).toHaveLength(8);
  });

  it("gives a new field a key nobody uses", () => {
    const first = newField("text", []);
    const second = newField("select", [first]);
    const third = newField("boolean", [{ ...second, key: "field_3" }, first]);

    expect([first.key, second.key, third.key]).toEqual(["field_1", "field_2", "field_4"]);
    expect(second.options).toEqual([]);
  });

  it("keeps the common settings and drops the old type's own when the type changes", () => {
    const select: FormField = {
      key: "field_1",
      type: "select",
      label: "Вид",
      required: true,
      help: "Подсказка",
      multiple: true,
      options: ["А"],
    };

    expect(withType(select, "number")).toEqual({
      key: "field_1",
      type: "number",
      label: "Вид",
      required: true,
      help: "Подсказка",
      integer: false,
      min: null,
      max: null,
      currency: null,
    });
  });

  it("sends only the settings of the field's own type", () => {
    const stray = { ...newField("boolean", []), label: "Срочно", options: ["x"], currency: "RUB" };
    expect(toPayload(stray)).toEqual({
      key: "field_1",
      type: "boolean",
      label: "Срочно",
      required: false,
      help: "",
    });
    expect(toPayload({ ...newField("number", []), label: "Сумма", currency: "rub" })).toMatchObject(
      { currency: "RUB", min: null, max: null, integer: false },
    );
  });

  it("reads lines and numbers the way people type them", () => {
    expect(linesOf(" Счёт \n\n Акт\n")).toEqual(["Счёт", "Акт"]);
    expect(toNumberOrNull("1,5")).toBe(1.5);
    expect(toNumberOrNull("  ")).toBeNull();
    expect(toNumberOrNull("много")).toBeNull();
  });
});
