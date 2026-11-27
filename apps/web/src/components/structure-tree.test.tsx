import type { Department, User } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { StructureTree } from "./structure-tree";

const fetchMock = vi.fn<typeof fetch>();

function somebody(id: string, name: string, responsibility = "") {
  return { id, crm_login: id, display_name: name, responsibility, is_active: true };
}

const pavel = somebody("u-pavel", "Павел Орлов", "План продаж");
const olga = somebody("u-olga", "Ольга Смирнова");
const anna = somebody("u-anna", "Анна Петрова");
const vera = somebody("u-vera", "Вера Лаптева");

const sales: Department = {
  id: "d-sales",
  name: "Продажи",
  is_active: true,
  members: [{ ...anna, is_primary: true }],
  managers: [
    { ...pavel, is_designated: true },
    { ...olga, is_designated: false },
  ],
};
const support: Department = {
  id: "d-support",
  name: "Поддержка",
  is_active: true,
  members: [],
  managers: [],
};

const users: User[] = [pavel, olga, anna, vera].map((one) => ({
  ...one,
  email: null,
  telegram_bound: true,
  has_password: true,
  created_at: "2026-11-01T00:00:00Z",
  departments: [],
}));

function show(overrides: Partial<Parameters<typeof StructureTree>[0]> = {}) {
  return renderWithIntl(
    <StructureTree
      initialDepartments={[sales, support]}
      users={users}
      canEdit
      canManage
      initialHead={{ title: "", user: null }}
      {...overrides}
    />,
  );
}

function answer(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sent(index: number) {
  const [path, init] = fetchMock.mock.calls[index] ?? [];
  return {
    path,
    method: init?.method,
    body: init?.body ? (JSON.parse(String(init.body)) as unknown) : undefined,
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StructureTree", () => {
  it("draws the top, the departments, their managers and the employees under them", () => {
    show();

    expect(screen.getByText("Компания")).toBeInTheDocument();
    // Each level is a branch of the one above.
    const departments = screen.getByRole("list", { name: "Отделы" });
    const managers = within(departments).getByRole("list", { name: "Руководители: Продажи" });
    expect(within(managers).getByText("Павел Орлов")).toBeInTheDocument();
    expect(within(managers).getByText("руководитель, ответственный")).toBeInTheDocument();
    expect(within(managers).getByText("Отвечает за: План продаж")).toBeInTheDocument();
    expect(within(managers).getByText("Ольга Смирнова")).toBeInTheDocument();

    const staff = within(managers).getByRole("list", { name: "Сотрудники: Продажи" });
    expect(within(staff).getByText("Анна Петрова")).toBeInTheDocument();
    expect(within(staff).getByText("Зона ответственности не указана")).toBeInTheDocument();

    const empty = within(departments).getByRole("list", { name: "Руководители: Поддержка" });
    expect(within(empty).getByText("Руководитель не назначен")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Сотрудники: Поддержка" })).not.toBeInTheDocument();

    expect(
      within(screen.getByRole("region", { name: "Без отдела" })).getByText("Вера Лаптева"),
    ).toBeInTheDocument();
  });

  it("saves what a person answers for", async () => {
    fetchMock.mockResolvedValueOnce(answer({ id: anna.id, responsibility: "Входящие заявки" }));
    show();

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Анна Петрова" }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "Отвечает за: Анна Петрова" }),
      "Входящие заявки",
    );
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Отвечает за: Входящие заявки")).toBeInTheDocument();
    expect(sent(0)).toEqual({
      path: "/api/v1/users/u-anna",
      method: "PATCH",
      body: { responsibility: "Входящие заявки" },
    });
  });

  it("puts an employee into a department, and the tree shows them at once", async () => {
    fetchMock.mockResolvedValueOnce(
      answer({ ...support, members: [{ ...vera, is_primary: true }] }),
    );
    show();

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Добавить сотрудника: Поддержка" }),
      "u-vera",
    );
    const box = screen.getByRole("combobox", { name: "Добавить сотрудника: Поддержка" });
    await userEvent.click(within(box.closest("form") as HTMLElement).getByRole("button"));

    const staff = await screen.findByRole("list", { name: "Сотрудники: Поддержка" });
    expect(within(staff).getByText("Вера Лаптева")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Без отдела" })).not.toBeInTheDocument();
    expect(sent(0)).toEqual({
      path: "/api/v1/departments/d-support/members",
      method: "POST",
      body: { user_id: "u-vera" },
    });
  });

  it("moves an employee to another department: in first, then out", async () => {
    fetchMock
      .mockResolvedValueOnce(answer({ ...support, members: [{ ...anna, is_primary: true }] }))
      .mockResolvedValueOnce(answer({ ...sales, members: [] }));
    show();

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Анна Петрова" }));
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Перевести в отдел: Анна Петрова" }),
      "d-support",
    );
    await userEvent.click(screen.getByRole("button", { name: "Перевести" }));

    const staff = await screen.findByRole("list", { name: "Сотрудники: Поддержка" });
    expect(within(staff).getByText("Анна Петрова")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Сотрудники: Продажи" })).not.toBeInTheDocument();
    expect(sent(0)).toEqual({
      path: "/api/v1/departments/d-support/members",
      method: "POST",
      body: { user_id: "u-anna", is_primary: true },
    });
    expect(sent(1)).toMatchObject({
      path: "/api/v1/departments/d-sales/members/u-anna",
      method: "DELETE",
    });
  });

  it("makes an employee a manager and takes a manager off", async () => {
    fetchMock
      .mockResolvedValueOnce(
        answer({ ...sales, managers: [...sales.managers, { ...anna, is_designated: false }] }),
      )
      .mockResolvedValueOnce(answer({ ...sales, managers: [sales.managers[0]] }));
    show();

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Анна Петрова" }));
    await userEvent.click(screen.getByRole("button", { name: "Сделать руководителем" }));
    const managers = await screen.findByRole("list", { name: "Руководители: Продажи" });
    expect(within(managers).getAllByText("руководитель")).toHaveLength(2);
    expect(sent(0)).toEqual({
      path: "/api/v1/departments/d-sales/managers",
      method: "POST",
      body: { user_id: "u-anna" },
    });

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Ольга Смирнова" }));
    await userEvent.click(screen.getByRole("button", { name: "Снять с руководства" }));
    expect(sent(1)).toMatchObject({
      path: "/api/v1/departments/d-sales/managers/u-olga",
      method: "DELETE",
    });
  });

  it("explains a refusal and leaves the tree as it was", async () => {
    fetchMock.mockResolvedValueOnce(
      answer({ error: { code: "designated_manager_required", message: "", details: null } }, 400),
    );
    show();

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Павел Орлов" }));
    await userEvent.click(screen.getByRole("button", { name: "Снять с руководства" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сначала назначьте ответственным другого руководителя отдела.",
    );
    expect(screen.getByText("руководитель, ответственный")).toBeInTheDocument();
  });

  it("is read-only for somebody who may only look", () => {
    show({
      canEdit: false,
      canManage: false,
      users: null,
      initialHead: { title: "Директор", user: null },
    });

    expect(screen.getByText("Директор")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("names the top of the tree and attaches an account to it", async () => {
    fetchMock.mockResolvedValueOnce(answer({ title: "Директор", user: pavel }));
    show();

    await userEvent.click(screen.getByRole("button", { name: "Изменить верх дерева" }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "Подпись наверху дерева" }),
      "Директор",
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Учётная запись" }),
      "u-pavel",
    );
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Директор")).toBeInTheDocument();
    expect(screen.queryByText("Компания")).not.toBeInTheDocument();
    expect(sent(0)).toEqual({
      path: "/api/v1/structure/head",
      method: "PATCH",
      body: { title: "Директор", user_id: "u-pavel" },
    });
  });
});
