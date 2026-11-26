import type { Template } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { TemplatesPanel } from "./templates-panel";

const fetchMock = vi.fn<typeof fetch>();
const departments = [
  { id: "d-sales", name: "Продажи" },
  { id: "d-support", name: "Поддержка" },
];

const invoice: Template = {
  id: "t-1",
  name: "Счёт клиенту",
  description: "",
  is_active: true,
  departments: [],
  draft_fields: [],
  draft_checkpoints: [],
  has_unpublished_changes: true,
  versions: [],
};

const version = {
  number: 1,
  published_at: "2026-11-26T10:00:00Z",
  published_by: "Администратор",
  form_fields: [{ key: "field_1" }],
  checkpoints: [],
};

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
  vi.restoreAllMocks();
});

describe("TemplatesPanel", () => {
  it("shows what state each template is in", () => {
    renderWithIntl(
      <TemplatesPanel
        initialTemplates={[
          invoice,
          {
            ...invoice,
            id: "t-2",
            name: "Отпуск",
            departments: [departments[0]!],
            has_unpublished_changes: false,
            versions: [version],
          },
          { ...invoice, id: "t-3", name: "Старый", is_active: false, versions: [version] },
        ]}
        departments={departments}
      />,
    );

    const first = within(screen.getByRole("region", { name: "Счёт клиенту" }));
    expect(first.getByText("не опубликован")).toBeInTheDocument();
    expect(first.getByText("Недоступен ни одному отделу")).toBeInTheDocument();
    const second = within(screen.getByRole("region", { name: "Отпуск" }));
    expect(second.getByText("опубликована версия 1")).toBeInTheDocument();
    expect(second.getByText("Доступен отделам: Продажи")).toBeInTheDocument();
    // Nothing new to publish; a retired template cannot be published at all.
    expect(second.queryByRole("button", { name: "Опубликовать" })).toBeNull();
    const third = within(screen.getByRole("region", { name: "Старый" }));
    expect(third.getByText("снят с использования")).toBeInTheDocument();
    expect(third.queryByRole("button", { name: "Опубликовать" })).toBeNull();
    expect(third.getByRole("button", { name: "Вернуть в использование" })).toBeInTheDocument();
  });

  it("creates a template and opens its editor", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json(invoice, { status: 201 }));
    renderWithIntl(<TemplatesPanel initialTemplates={[]} departments={departments} />);

    await user.type(screen.getByLabelText("Название шаблона"), "Счёт клиенту");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(
      await screen.findByRole("form", { name: "Редактирование: Счёт клиенту" }),
    ).toBeInTheDocument();
    expect(lastCall()).toEqual({
      url: "/api/v1/request-templates",
      method: "POST",
      body: { name: "Счёт клиенту" },
    });
  });

  it("builds a form from fields of different types and saves the draft", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json({ ...invoice, departments: [departments[0]] }));
    renderWithIntl(<TemplatesPanel initialTemplates={[invoice]} departments={departments} />);
    await user.click(screen.getByRole("button", { name: "Редактировать" }));
    const editor = within(screen.getByRole("form", { name: "Редактирование: Счёт клиенту" }));

    await user.click(editor.getByRole("checkbox", { name: "Продажи" }));
    // A text field.
    await user.click(editor.getByRole("button", { name: "Добавить поле" }));
    const text = within(editor.getByRole("group", { name: /Поле 1/ }));
    await user.type(text.getByLabelText("Название поля"), "Клиент");
    await user.click(text.getByRole("checkbox", { name: "Обязательное" }));
    // A money field.
    await user.selectOptions(editor.getAllByLabelText("Тип").at(-1)!, "number");
    await user.click(editor.getByRole("button", { name: "Добавить поле" }));
    const money = within(editor.getByRole("group", { name: /Поле 2/ }));
    await user.type(money.getByLabelText("Название поля"), "Сумма");
    await user.type(money.getByLabelText(/Валюта/), "rub");
    await user.type(money.getByLabelText("Минимум"), "0");
    // A list.
    await user.selectOptions(editor.getAllByLabelText("Тип").at(-1)!, "select");
    await user.click(editor.getByRole("button", { name: "Добавить поле" }));
    const list = within(editor.getByRole("group", { name: /Поле 3/ }));
    await user.type(list.getByLabelText("Название поля"), "Вид");
    await user.type(list.getByLabelText(/Варианты/), "Счёт{Enter}Акт");
    await user.type(editor.getByLabelText("Каждый пункт с новой строки"), "Проверить реквизиты");

    await user.click(editor.getByRole("button", { name: "Сохранить черновик" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Черновик сохранён.");
    expect(lastCall()).toEqual({
      url: "/api/v1/request-templates/t-1",
      method: "PATCH",
      body: {
        name: "Счёт клиенту",
        description: "",
        department_ids: ["d-sales"],
        draft_fields: [
          {
            key: "field_1",
            type: "text",
            label: "Клиент",
            required: true,
            help: "",
            multiline: false,
          },
          {
            key: "field_2",
            type: "number",
            label: "Сумма",
            required: false,
            help: "",
            integer: false,
            min: 0,
            max: null,
            currency: "RUB",
          },
          {
            key: "field_3",
            type: "select",
            label: "Вид",
            required: false,
            help: "",
            multiple: false,
            options: ["Счёт", "Акт"],
          },
        ],
        draft_checkpoints: ["Проверить реквизиты"],
      },
    });
  });

  it("reorders and removes fields", async () => {
    const user = userEvent.setup();
    const two = {
      ...invoice,
      draft_fields: [
        { key: "a", type: "boolean", label: "Первое", required: false, help: "" },
        { key: "b", type: "boolean", label: "Второе", required: false, help: "" },
      ],
    };
    fetchMock.mockResolvedValueOnce(Response.json(two));
    renderWithIntl(<TemplatesPanel initialTemplates={[two]} departments={departments} />);
    await user.click(screen.getByRole("button", { name: "Редактировать" }));
    const editor = within(screen.getByRole("form"));

    await user.click(
      within(editor.getByRole("group", { name: "Поле 2: Второе" })).getByRole("button", {
        name: "Выше",
      }),
    );
    await user.click(
      within(editor.getByRole("group", { name: "Поле 2: Первое" })).getByRole("button", {
        name: "Удалить поле",
      }),
    );
    await user.click(editor.getByRole("button", { name: "Сохранить черновик" }));

    expect(lastCall().body.draft_fields.map((field: { key: string }) => field.key)).toEqual(["b"]);
  });

  it("publishes after a confirmation", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...invoice, has_unpublished_changes: false, versions: [version] }),
    );
    renderWithIntl(<TemplatesPanel initialTemplates={[invoice]} departments={departments} />);

    await user.click(screen.getByRole("button", { name: "Опубликовать" }));

    expect(confirm).toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent("Опубликована версия 1.");
    expect(lastCall().url).toBe("/api/v1/request-templates/t-1/publish");
    expect(screen.queryByRole("button", { name: "Опубликовать" })).toBeNull();
  });

  it("does not publish when the confirmation is declined", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWithIntl(<TemplatesPanel initialTemplates={[invoice]} departments={departments} />);

    await user.click(screen.getByRole("button", { name: "Опубликовать" }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retires a template", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json({ ...invoice, is_active: false }));
    renderWithIntl(<TemplatesPanel initialTemplates={[invoice]} departments={departments} />);

    await user.click(screen.getByRole("button", { name: "Снять с использования" }));

    expect(await screen.findByText("снят с использования")).toBeInTheDocument();
    expect(lastCall().body).toEqual({ is_active: false });
  });

  it("explains a refusal and keeps the editor open", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code: "invalid_template", message: "x" } }, { status: 400 }),
    );
    renderWithIntl(<TemplatesPanel initialTemplates={[invoice]} departments={departments} />);
    await user.click(screen.getByRole("button", { name: "Редактировать" }));

    await user.click(screen.getByRole("button", { name: "Сохранить черновик" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Проверьте поля формы");
    expect(screen.getByRole("form", { name: /Редактирование/ })).toBeInTheDocument();
  });
});
