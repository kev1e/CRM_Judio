import type { WorkflowStatus } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { WorkflowPanel } from "./workflow-panel";

const fetchMock = vi.fn<typeof fetch>();

function status(id: string, name: string, category: WorkflowStatus["category"]): WorkflowStatus {
  return { id, name, category, position: 0, is_active: true, next_status_ids: [], task_count: 0 };
}

const todo = { ...status("s-todo", "Нужно сделать", "new"), next_status_ids: ["s-doing"] };
const doing = { ...status("s-doing", "В работе", "active"), task_count: 3 };
const done = status("s-done", "Готово", "completed");
const cancelled = status("s-cancelled", "Отменено", "cancelled");
const all = [todo, doing, done, cancelled];

function section(name: string) {
  return within(screen.getByRole("region", { name }));
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? [];
  return { url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null };
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WorkflowPanel", () => {
  it("shows each status with its type, task count and allowed moves", () => {
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    expect(section("В работе").getByText("В работе · Задач: 3")).toBeInTheDocument();
    expect(section("Нужно сделать").getByRole("checkbox", { name: "В работе" })).toBeChecked();
    expect(section("Нужно сделать").getByRole("checkbox", { name: "Готово" })).not.toBeChecked();
    // A status never leads to itself.
    expect(section("Нужно сделать").queryByRole("checkbox", { name: "Нужно сделать" })).toBeNull();
  });

  it("offers no moves out of a completed status", () => {
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    expect(section("Готово").queryByRole("checkbox")).toBeNull();
    expect(section("Готово").getByText(/Вернуть её можно только/)).toBeInTheDocument();
  });

  it("adds a status", async () => {
    const user = userEvent.setup();
    const review = status("s-review", "На проверке", "active");
    fetchMock.mockResolvedValueOnce(Response.json({ results: [...all, review] }, { status: 201 }));
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);
    const form = within(screen.getByRole("form", { name: "Новый статус" }));

    await user.type(form.getByLabelText("Название статуса"), "На проверке");
    await user.selectOptions(form.getByLabelText("Тип"), "active");
    await user.click(form.getByRole("button", { name: "Добавить" }));

    expect(await screen.findByRole("region", { name: "На проверке" })).toBeInTheDocument();
    expect(lastCall()).toEqual({
      url: "/api/v1/workflow/statuses",
      method: "POST",
      body: { name: "На проверке", category: "active" },
    });
  });

  it("allows a move by ticking it", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({
        results: [{ ...todo, next_status_ids: ["s-doing", "s-done"] }, doing, done, cancelled],
      }),
    );
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    await user.click(section("Нужно сделать").getByRole("checkbox", { name: "Готово" }));

    expect(await section("Нужно сделать").findByRole("checkbox", { name: "Готово" })).toBeChecked();
    expect(lastCall()).toEqual({
      url: "/api/v1/workflow/statuses/s-todo",
      method: "PATCH",
      body: { next_status_ids: ["s-doing", "s-done"] },
    });
  });

  it("moves a column down by sending the whole new order", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json({ results: [doing, todo, done, cancelled] }));
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    expect(section("Нужно сделать").getByRole("button", { name: "Выше" })).toBeDisabled();
    await user.click(section("Нужно сделать").getByRole("button", { name: "Ниже" }));

    expect(lastCall()).toEqual({
      url: "/api/v1/workflow/order",
      method: "POST",
      body: { status_ids: ["s-doing", "s-todo", "s-done", "s-cancelled"] },
    });
    expect(await section("В работе").findByRole("button", { name: "Выше" })).toBeDisabled();
  });

  it("renames a status", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ results: [{ ...todo, name: "Очередь" }, doing, done, cancelled] }),
    );
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    await user.click(section("Нужно сделать").getByRole("button", { name: "Переименовать" }));
    const field = section("Нужно сделать").getByLabelText("Название статуса");
    await user.clear(field);
    await user.type(field, "Очередь");
    await user.click(section("Нужно сделать").getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByRole("region", { name: "Очередь" })).toBeInTheDocument();
    expect(lastCall().body).toEqual({ name: "Очередь" });
  });

  it("retires a used status only with a replacement of the same kind", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({
        results: [
          { ...todo, next_status_ids: [], task_count: 3 },
          done,
          cancelled,
          { ...doing, is_active: false, task_count: 0 },
        ],
      }),
    );
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    await user.click(section("В работе").getByRole("button", { name: "Убрать с доски" }));
    const form = within(screen.getByRole("form", { name: "Убрать статус «В работе»" }));
    expect(form.getByText(/Задач в этом статусе: 3/)).toBeInTheDocument();
    const select = form.getByLabelText("Заменить на");
    expect(select).toBeRequired();
    expect(
      within(select)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Не выбрано", "Нужно сделать"]);

    await user.selectOptions(select, "Нужно сделать");
    await user.click(form.getByRole("button", { name: "Убрать статус" }));

    expect(lastCall()).toEqual({
      url: "/api/v1/workflow/statuses/s-doing/retire",
      method: "POST",
      body: { replacement_id: "s-todo" },
    });
    const retired = within(await screen.findByRole("region", { name: "Убранные статусы" }));
    expect(retired.getByText("В работе")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "В работе" })).toBeNull();
  });

  it("retires an unused status without a replacement", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ results: [todo, doing, done, { ...cancelled, is_active: false }] }),
    );
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    await user.click(section("Отменено").getByRole("button", { name: "Убрать с доски" }));
    await user.click(screen.getByRole("button", { name: "Убрать статус" }));

    expect(lastCall().body).toEqual({ replacement_id: null });
    expect(await screen.findByRole("region", { name: "Убранные статусы" })).toBeInTheDocument();
  });

  it("returns a retired status to the board", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json({ results: all }));
    renderWithIntl(
      <WorkflowPanel initialStatuses={[todo, doing, done, { ...cancelled, is_active: false }]} />,
    );

    await user.click(screen.getByRole("button", { name: "Вернуть на доску" }));

    expect(lastCall().url).toBe("/api/v1/workflow/statuses/s-cancelled/restore");
    expect(await screen.findByRole("region", { name: "Отменено" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Убранные статусы" })).toBeNull();
  });

  it("explains a refusal and changes nothing", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code: "last_new_status", message: "x" } }, { status: 400 }),
    );
    renderWithIntl(<WorkflowPanel initialStatuses={all} />);

    await user.click(section("Нужно сделать").getByRole("button", { name: "Убрать с доски" }));
    await user.click(screen.getByRole("button", { name: "Убрать статус" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Нужен хотя бы один статус типа");
    expect(screen.getByRole("region", { name: "Нужно сделать" })).toBeInTheDocument();
  });
});
