import type { RequestForm } from "@crm/contracts";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { NewRequestDialog } from "./new-request-dialog";

const fetchMock = vi.fn<typeof fetch>();
const field = { required: false, help: "" };
const invoice: RequestForm = {
  id: "t-1",
  name: "Счёт клиенту",
  description: "Счёт на оплату",
  version: 3,
  departments: [
    { id: "d-sales", name: "Продажи" },
    { id: "d-support", name: "Поддержка" },
  ],
  form_fields: [
    { ...field, key: "client", type: "text", label: "Клиент", required: true, max_length: 500 },
    { ...field, key: "amount", type: "number", label: "Сумма", currency: "RUB" },
    { ...field, key: "kind", type: "select", label: "Вид", options: ["Счёт", "Акт"] },
    {
      ...field,
      key: "tags",
      type: "select",
      label: "Метки",
      options: ["Новый", "VIP"],
      multiple: true,
    },
    { ...field, key: "owner", type: "employee", label: "Куратор" },
    { ...field, key: "urgent", type: "boolean", label: "Срочно", help: "Нужно сегодня" },
    { ...field, key: "scan", type: "file", label: "Скан" },
  ],
};
const leave: RequestForm = {
  id: "t-2",
  name: "Отпуск",
  description: "",
  version: 1,
  departments: [{ id: "d-sales", name: "Продажи" }],
  form_fields: [{ ...field, key: "reason", type: "text", label: "Причина" }],
};
const people: Record<string, { id: string; name: string }[]> = {
  "d-sales": [
    { id: "u-anna", name: "Анна" },
    { id: "u-boris", name: "Борис" },
  ],
  "d-support": [{ id: "u-vera", name: "Вера" }],
};

function json(body: unknown, status = 200) {
  return Promise.resolve(Response.json(body, { status }));
}

function serve(forms: RequestForm[], submit: () => Promise<Response> = () => json({}, 500)) {
  fetchMock.mockImplementation((input, init) => {
    const url = String(input);
    if (url.includes("/request-forms")) {
      return json({ results: forms });
    }
    if (url.includes("/task-assignees")) {
      const id = new URL(url, "http://x").searchParams.get("department_id") ?? "";
      return json({ results: people[id] ?? [] });
    }
    if (url.endsWith("/requests") && init?.method === "POST") {
      return submit();
    }
    return json({}, 404);
  });
}

function submitted() {
  const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/requests"));
  const body = call?.[1]?.body as FormData;
  return { body, payload: JSON.parse(String(body.get("payload"))) as Record<string, unknown> };
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NewRequestDialog", () => {
  it("explains when no form is available", async () => {
    serve([]);
    renderWithIntl(<NewRequestDialog onClose={vi.fn()} onCreated={vi.fn()} />);

    expect(
      await screen.findByText(/Нет шаблонов, по которым вы можете подать заявку/),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "Подать заявку" })).not.toBeInTheDocument();
  });

  it("renders the published form and sends values and files", async () => {
    const created = { id: "task-1", title: "Счёт для «Ромашки»", task: null };
    serve([invoice, leave], () => json(created, 201));
    const onCreated = vi.fn();
    const user = userEvent.setup();
    renderWithIntl(<NewRequestDialog onClose={vi.fn()} onCreated={onCreated} />);

    const title = await screen.findByLabelText("Название");
    expect(title).toHaveValue("Счёт клиенту");
    expect(screen.getByText("Счёт на оплату")).toBeVisible();
    expect(screen.getByText("Нужно сегодня")).toBeVisible();
    await screen.findAllByRole("option", { name: "Анна" });

    await user.clear(title);
    await user.type(title, "Счёт для «Ромашки»");
    await user.selectOptions(screen.getByLabelText("Исполнитель"), "u-anna");
    await user.type(screen.getByLabelText(/^Клиент/), "ООО Ромашка");
    await user.type(screen.getByLabelText(/^Сумма/), "150,50");
    await user.selectOptions(screen.getByLabelText(/^Вид/), "Акт");
    await user.click(screen.getByRole("checkbox", { name: "VIP" }));
    await user.selectOptions(screen.getByLabelText(/^Куратор/), "u-boris");
    await user.selectOptions(screen.getByLabelText(/^Срочно/), "true");
    const file = new File(["%PDF-1.7"], "scan.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/^Скан/), file);
    await user.click(screen.getByRole("button", { name: "Подать заявку" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
    const { body, payload } = submitted();
    expect(payload).toEqual({
      template_id: "t-1",
      version: 3,
      department_id: "d-sales",
      assignee_id: "u-anna",
      title: "Счёт для «Ромашки»",
      priority: "normal",
      due_at: null,
      values: {
        client: "ООО Ромашка",
        amount: "150,50",
        kind: "Акт",
        tags: ["VIP"],
        owner: "u-boris",
        urgent: true,
      },
    });
    expect((body.get("file.scan") as File).name).toBe("scan.pdf");
  });

  it("offers people of the chosen department and forgets those of another", async () => {
    serve([invoice]);
    const user = userEvent.setup();
    renderWithIntl(<NewRequestDialog onClose={vi.fn()} onCreated={vi.fn()} />);

    await screen.findAllByRole("option", { name: "Анна" });
    await user.selectOptions(screen.getByLabelText(/^Куратор/), "u-boris");
    await user.selectOptions(screen.getByLabelText("Ответственный отдел"), "d-support");

    await waitFor(() => expect(screen.getAllByRole("option", { name: "Вера" })).toHaveLength(2));
    expect(screen.queryByRole("option", { name: "Борис" })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Куратор/)).toHaveValue("");
  });

  it("starts another form from empty answers", async () => {
    serve([invoice, leave]);
    const user = userEvent.setup();
    renderWithIntl(<NewRequestDialog onClose={vi.fn()} onCreated={vi.fn()} />);

    await user.type(await screen.findByLabelText(/^Клиент/), "Ромашка");
    await user.selectOptions(screen.getByLabelText("Шаблон"), "t-2");

    expect(screen.queryByLabelText(/^Клиент/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/^Причина/)).toHaveValue("");
    expect(screen.getByLabelText("Название")).toHaveValue("Отпуск");
  });

  it("names the field the server refused", async () => {
    serve([invoice], () =>
      json(
        {
          error: {
            code: "invalid_form_value",
            message: "x",
            details: { field: "amount", reason: "out_of_range" },
          },
        },
        400,
      ),
    );
    const user = userEvent.setup();
    renderWithIntl(<NewRequestDialog onClose={vi.fn()} onCreated={vi.fn()} />);

    await screen.findAllByRole("option", { name: "Анна" });
    await user.selectOptions(screen.getByLabelText("Исполнитель"), "u-anna");
    await user.type(screen.getByLabelText(/^Клиент/), "Ромашка");
    await user.click(screen.getByRole("button", { name: "Подать заявку" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Поле «Сумма»: значение вне допустимых границ.",
    );
  });

  it("tells to reopen a form that has changed", async () => {
    serve([leave], () =>
      json({ error: { code: "template_changed", message: "x", details: null } }, 409),
    );
    const user = userEvent.setup();
    renderWithIntl(<NewRequestDialog onClose={vi.fn()} onCreated={vi.fn()} />);

    await screen.findAllByRole("option", { name: "Анна" });
    await user.selectOptions(screen.getByLabelText("Исполнитель"), "u-anna");
    await user.click(screen.getByRole("button", { name: "Подать заявку" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Шаблон изменился");
  });
});
