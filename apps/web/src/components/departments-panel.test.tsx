import type { Department } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { DepartmentsPanel, type Person } from "./departments-panel";

const fetchMock = vi.fn<typeof fetch>();

const anna = {
  id: "u-anna",
  crm_login: "anna",
  display_name: "Анна Петрова",
  responsibility: "",
  is_active: true,
};
const olga = {
  id: "u-olga",
  crm_login: "olga",
  display_name: "Ольга Смирнова",
  responsibility: "",
  is_active: true,
};
const people: Person[] = [anna, olga];

const sales: Department = {
  id: "d-sales",
  name: "Продажи",
  is_active: true,
  members: [{ ...anna, is_primary: true }],
  managers: [{ ...olga, is_designated: true }],
};

function section(name: string) {
  return within(screen.getByRole("region", { name: new RegExp(name) }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DepartmentsPanel", () => {
  it("shows who belongs to a department and who manages it", () => {
    renderWithIntl(<DepartmentsPanel initialDepartments={[sales]} people={people} canManage />);

    const items = section("Продажи")
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(items).toEqual([
      expect.stringContaining("Ольга Смирнова (ответственный)"),
      expect.stringContaining("Анна Петрова (основной отдел)"),
    ]);
  });

  it("is read-only for somebody who may only look", () => {
    renderWithIntl(<DepartmentsPanel initialDepartments={[sales]} people={[]} canManage={false} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Название отдела")).not.toBeInTheDocument();
  });

  it("creates a department and shows it", async () => {
    const user = userEvent.setup();
    const support: Department = {
      ...sales,
      id: "d-support",
      name: "Поддержка",
      members: [],
      managers: [],
    };
    fetchMock.mockResolvedValueOnce(Response.json(support, { status: 201 }));
    renderWithIntl(<DepartmentsPanel initialDepartments={[sales]} people={people} canManage />);

    await user.type(screen.getByLabelText("Название отдела"), "Поддержка");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByRole("region", { name: /Поддержка/ })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/departments");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Поддержка" });
    expect(screen.getByLabelText("Название отдела")).toHaveValue("");
  });

  it("adds a member, offering only people who are not in the department yet", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...sales, members: [...sales.members, { ...olga, is_primary: false }] }),
    );
    renderWithIntl(<DepartmentsPanel initialDepartments={[sales]} people={people} canManage />);
    const select = section("Продажи").getByRole("combobox", { name: "Добавить сотрудника" });

    expect(within(select).queryByRole("option", { name: "Анна Петрова" })).toBeNull();
    await user.selectOptions(select, "Ольга Смирнова");
    await user.click(
      within(select.closest("form") as HTMLElement).getByRole("button", { name: "Добавить" }),
    );

    expect(
      await section("Продажи").findByRole("button", { name: "Сделать основным: Ольга Смирнова" }),
    ).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/departments/d-sales/members");
    expect(JSON.parse(String(init?.body))).toEqual({ user_id: "u-olga" });
  });

  it("explains a refusal and changes nothing", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code: "department_is_primary", message: "x" } }, { status: 400 }),
    );
    renderWithIntl(<DepartmentsPanel initialDepartments={[sales]} people={people} canManage />);

    await user.click(section("Продажи").getByRole("button", { name: "Закрыть отдел" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сначала переведите их в другой отдел.",
    );
    expect(section("Продажи").getByRole("button", { name: "Закрыть отдел" })).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "PATCH" });
  });

  it("removes a manager with a DELETE request", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json({ ...sales, managers: [] }));
    renderWithIntl(<DepartmentsPanel initialDepartments={[sales]} people={people} canManage />);

    await user.click(section("Продажи").getByRole("button", { name: "Убрать: Ольга Смирнова" }));

    expect(await section("Продажи").findByText("Никого нет")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/departments/d-sales/managers/u-olga");
    expect(init?.method).toBe("DELETE");
  });

  it("offers no changes inside a closed department except reopening it", () => {
    renderWithIntl(
      <DepartmentsPanel
        initialDepartments={[{ ...sales, is_active: false }]}
        people={people}
        canManage
      />,
    );

    expect(section("Продажи").queryByRole("combobox")).not.toBeInTheDocument();
    expect(section("Продажи").getByRole("button", { name: "Открыть отдел" })).toBeEnabled();
  });
});
