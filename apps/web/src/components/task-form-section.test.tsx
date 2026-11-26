import type { FormAnswer } from "@crm/contracts";
import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { TaskFormSection } from "./task-form-section";

const fetchMock = vi.fn<typeof fetch>();

function answer(key: string, type: string, value: unknown, extra: Partial<FormAnswer> = {}) {
  return {
    key,
    question: key,
    type,
    filled: true,
    value,
    currency: null,
    with_time: false,
    attachment_id: null,
    ...extra,
  } satisfies FormAnswer;
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TaskFormSection", () => {
  it("shows every answer in a readable form", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        form: {
          template_name: "Счёт клиенту",
          version: 2,
          answers: [
            answer("Клиент", "text", "ООО Ромашка"),
            answer("Сумма", "number", "150.50", { currency: "RUB" }),
            answer("Срок", "date", "2026-12-15"),
            answer("Метки", "select", ["Новый", "VIP"]),
            answer("Ответственный", "employee", "Борис"),
            answer("Срочно", "boolean", false),
            answer("Скан", "file", "scan.pdf", { attachment_id: "a-1" }),
            answer("Акт", "file", null),
            answer("Комментарий", "text", null, { filled: false }),
          ],
        },
      }),
    );
    renderWithIntl(<TaskFormSection taskId="task-1" revision={0} />);

    expect(await screen.findByRole("heading", { name: /Форма «Счёт клиенту»/ })).toBeVisible();
    expect(screen.getByText("версия 2")).toBeVisible();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/tasks/task-1/form");
    expect(screen.getByText("ООО Ромашка")).toBeVisible();
    expect(screen.getByText("150.50 RUB")).toBeVisible();
    expect(screen.getByText(/15 дек\. 2026/)).toBeVisible();
    expect(screen.getByText("Новый, VIP")).toBeVisible();
    expect(screen.getByText("Борис")).toBeVisible();
    expect(screen.getByText("Нет")).toBeVisible();
    expect(screen.getByRole("link", { name: "scan.pdf" })).toHaveAttribute(
      "href",
      "/api/v1/tasks/task-1/attachments/a-1",
    );
    expect(screen.getByText("файл удалён")).toBeVisible();
    expect(screen.getByText("не заполнено")).toBeVisible();
  });

  it("shows nothing for a request made without a form", async () => {
    fetchMock.mockResolvedValue(Response.json({ form: null }));
    const { container } = renderWithIntl(<TaskFormSection taskId="task-1" revision={0} />);

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
