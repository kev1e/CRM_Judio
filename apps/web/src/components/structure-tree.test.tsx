import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DepartmentNode, TreePerson } from "@/lib/structure";
import { renderWithIntl } from "@/test/render";

import { StructureTree } from "./structure-tree";

const fetchMock = vi.fn<typeof fetch>();

function somebody(id: string, name: string, responsibility = ""): TreePerson {
  return { id, crm_login: id, display_name: name, responsibility };
}

const pavel = somebody("u-pavel", "Павел Орлов", "План продаж");
const olga = somebody("u-olga", "Ольга Смирнова");
const anna = somebody("u-anna", "Анна Петрова");

const sales: DepartmentNode = {
  id: "d-sales",
  name: "Продажи",
  managers: [
    { ...pavel, is_designated: true },
    { ...olga, is_designated: false },
  ],
  employees: [anna],
};
const support: DepartmentNode = { id: "d-support", name: "Поддержка", managers: [], employees: [] };

function answer(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StructureTree", () => {
  it("shows the managers of a department and the employees under them", () => {
    renderWithIntl(
      <StructureTree initialTree={[sales, support]} initialUnplaced={null} canEdit canManage />,
    );

    // Company -> departments -> managers -> employees, each a branch of the one above.
    const departments = screen.getByRole("list", { name: "Отделы" });
    const managers = within(departments).getByRole("list", { name: "Руководители: Продажи" });
    expect(within(managers).getByText("Павел Орлов")).toBeInTheDocument();
    expect(within(managers).getByText("руководитель, ответственный")).toBeInTheDocument();
    expect(within(managers).getByText("Отвечает за: План продаж")).toBeInTheDocument();
    expect(within(managers).getByText("Ольга Смирнова")).toBeInTheDocument();

    // The employees are a branch inside the managers' one.
    const staff = within(managers).getByRole("list", { name: "Сотрудники: Продажи" });
    expect(within(staff).getByText("Анна Петрова")).toBeInTheDocument();
    expect(within(staff).getByText("Зона ответственности не указана")).toBeInTheDocument();

    const empty = within(departments).getByRole("list", { name: "Руководители: Поддержка" });
    expect(within(empty).getByText("Руководитель не назначен")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Сотрудники: Поддержка" })).not.toBeInTheDocument();
  });

  it("saves what a person answers for", async () => {
    fetchMock.mockResolvedValueOnce(answer({ id: anna.id, responsibility: "Входящие заявки" }));
    renderWithIntl(
      <StructureTree initialTree={[sales]} initialUnplaced={null} canEdit canManage />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Анна Петрова" }));
    await userEvent.type(
      screen.getByRole("textbox", { name: "Отвечает за: Анна Петрова" }),
      "Входящие заявки",
    );
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Отвечает за: Входящие заявки")).toBeInTheDocument();
    const [path, init] = fetchMock.mock.calls[0] ?? [];
    expect(path).toBe("/api/v1/users/u-anna");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ responsibility: "Входящие заявки" });
  });

  it("keeps the form open and explains a refusal", async () => {
    fetchMock.mockResolvedValueOnce(
      answer({ error: { code: "permission_denied", message: "", details: null } }, 403),
    );
    renderWithIntl(
      <StructureTree initialTree={[sales]} initialUnplaced={null} canEdit canManage />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Изменить: Анна Петрова" }));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Недостаточно прав.");
    expect(screen.getByRole("textbox", { name: "Отвечает за: Анна Петрова" })).toBeInTheDocument();
  });

  it("is read-only for somebody who may only look", () => {
    renderWithIntl(
      <StructureTree
        initialTree={[sales]}
        initialUnplaced={null}
        canEdit={false}
        canManage={false}
      />,
    );

    expect(screen.queryByRole("button", { name: /Изменить/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Изменить состав/ })).not.toBeInTheDocument();
  });

  it("lists the employees who are in no department yet", () => {
    renderWithIntl(
      <StructureTree
        initialTree={[sales]}
        initialUnplaced={[somebody("u-vera", "Вера Лаптева")]}
        canEdit
        canManage
      />,
    );

    expect(
      within(screen.getByRole("region", { name: "Без отдела" })).getByText("Вера Лаптева"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Изменить состав: Продажи" })).toHaveAttribute(
      "href",
      "/departments#department-d-sales",
    );
  });
});
