import type { Project } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { ProjectZones } from "./project-zones";

const sales = { id: "d-sales", name: "Продажи" };
const support = { id: "d-support", name: "Поддержка" };
const anna = { id: "u-anna", name: "Анна" };
const boris = { id: "u-boris", name: "Борис" };
const vera = { id: "u-vera", name: "Вера" };

const launch: Project = {
  id: "p-1",
  name: "Запуск",
  department: sales,
  is_active: true,
  members: [
    { user: anna, department: sales, is_active: true },
    { user: boris, department: sales, is_active: true },
    { user: vera, department: support, is_active: true },
  ],
  zones: [
    {
      id: "z-1",
      name: "Договоры",
      members: [
        { user: vera, is_responsible: true },
        { user: anna, is_responsible: false },
      ],
    },
  ],
  pending_invitations: [],
  can_manage: true,
};

function show(project: Project, editable = true) {
  const change = vi.fn(() => Promise.resolve(true));
  renderWithIntl(
    <ProjectZones project={project} editable={editable} busy={false} change={change} />,
  );
  return change;
}

describe("ProjectZones", () => {
  it("draws departments as circles and a shared zone on their overlap", () => {
    show(launch);

    const shared = within(screen.getByRole("group", { name: "Продажи + Поддержка" }));
    const zone = within(shared.getByRole("group", { name: "Зона: Договоры" }));
    expect(zone.getByText("Вера")).toBeInTheDocument();
    expect(zone.getByText("(Ответственный)")).toBeInTheDocument();
    expect(zone.getByText("Анна")).toBeInTheDocument();
    // Boris stands in no zone: he is in the circle of his own department.
    expect(
      within(screen.getByRole("group", { name: "Продажи" })).getByText("Борис"),
    ).toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "Поддержка" })).queryByText("Вера")).toBeNull();
  });

  it("a new project has its picture at once", () => {
    show({ ...launch, members: [], zones: [] });

    expect(screen.getByRole("group", { name: "Продажи" })).toBeInTheDocument();
  });

  it("adds a zone, puts a participant into it and marks who answers for it", async () => {
    const change = show(launch);

    await userEvent.type(
      screen.getByRole("textbox", { name: "Название новой зоны: Запуск" }),
      "Склад",
    );
    await userEvent.click(screen.getByRole("button", { name: "Добавить зону" }));
    expect(change).toHaveBeenLastCalledWith("/api/v1/projects/p-1/zones", "POST", {
      name: "Склад",
    });

    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Добавить в зону: Договоры" }),
      "u-boris",
    );
    await userEvent.click(screen.getByRole("button", { name: "Добавить" }));
    expect(change).toHaveBeenLastCalledWith("/api/v1/projects/p-1/zones/z-1/members", "POST", {
      user_id: "u-boris",
    });

    await userEvent.click(screen.getByRole("button", { name: "Ответственный: Анна, Договоры" }));
    expect(change).toHaveBeenLastCalledWith("/api/v1/projects/p-1/zones/z-1/members", "POST", {
      user_id: "u-anna",
      is_responsible: true,
    });

    await userEvent.click(screen.getByRole("button", { name: "Убрать из зоны: Вера, Договоры" }));
    expect(change).toHaveBeenLastCalledWith(
      "/api/v1/projects/p-1/zones/z-1/members/u-vera",
      "DELETE",
    );
    await userEvent.click(screen.getByRole("button", { name: "Удалить зону: Договоры" }));
    expect(change).toHaveBeenLastCalledWith("/api/v1/projects/p-1/zones/z-1", "DELETE");
  });

  it("is a picture only for somebody who does not run the project", () => {
    show(launch, false);

    expect(screen.getByRole("group", { name: "Зона: Договоры" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
