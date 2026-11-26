import { describe, expect, it } from "vitest";

import type { FormField } from "./form-fields";
import { emptyValues, toReason, toSubmission } from "./request-form";

const base = { required: false, help: "" };
const fields: FormField[] = [
  { ...base, key: "client", type: "text", label: "Клиент" },
  { ...base, key: "amount", type: "number", label: "Сумма" },
  { ...base, key: "day", type: "date", label: "День" },
  { ...base, key: "moment", type: "date", label: "Время", with_time: true },
  { ...base, key: "tags", type: "select", label: "Метки", multiple: true, options: ["A", "B"] },
  { ...base, key: "urgent", type: "boolean", label: "Срочно" },
  { ...base, key: "scan", type: "file", label: "Скан" },
];

describe("request form values", () => {
  it("starts empty, with a list for a multiple choice", () => {
    expect(emptyValues(fields)).toEqual({
      client: "",
      amount: "",
      day: "",
      moment: "",
      tags: [],
      urgent: "",
      scan: null,
    });
  });

  it("sends only what was filled in, files apart from values", () => {
    const file = new File(["%PDF"], "scan.pdf");
    const sent = toSubmission(fields, {
      client: "Ромашка",
      amount: "150,50",
      day: "2026-12-15",
      moment: "2026-12-01T12:30",
      tags: ["B"],
      urgent: "false",
      scan: file,
    });

    expect(sent.values).toEqual({
      client: "Ромашка",
      amount: "150,50",
      day: "2026-12-15",
      moment: new Date("2026-12-01T12:30").toISOString(),
      tags: ["B"],
      urgent: false,
    });
    expect([...sent.files]).toEqual([["scan", file]]);
  });

  it("leaves empty answers out", () => {
    const sent = toSubmission(fields, { ...emptyValues(fields), client: "  " });

    expect(sent.values).toEqual({});
    expect(sent.files.size).toBe(0);
  });

  it("falls back to a general reason for an unknown one", () => {
    expect(toReason("too_long")).toBe("too_long");
    expect(toReason("something_new")).toBe("invalid");
    expect(toReason(undefined)).toBe("invalid");
  });
});
