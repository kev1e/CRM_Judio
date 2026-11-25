import type { Candidate, Project, ProjectInvitation, ProjectList } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { ProjectsPanel } from "./projects-panel";

const fetchMock = vi.fn<typeof fetch>();

const sales = { id: "d-sales", name: "Продажи" };
const support = { id: "d-support", name: "Поддержка" };
const anna: Candidate = { id: "u-anna", name: "Анна Петрова", departments: [sales] };
const vera: Candidate = { id: "u-vera", name: "Вера Орлова", departments: [support] };

const launch: Project = {
  id: "p-1",
  name: "Запуск продукта",
  department: sales,
  is_active: true,
  members: [],
  pending_invitations: [],
  can_manage: true,
};

const veraInvitation: ProjectInvitation = {
  id: "i-1",
  project: { id: "p-1", name: "Запуск продукта" },
  project_department: sales,
  user: { id: "u-vera", name: "Вера Орлова" },
  department: support,
  requested_by: { id: "u-olga", name: "Ольга Смирнова" },
  created_at: "2026-11-26T10:00:00Z",
};

function list(overrides: Partial<ProjectList> = {}): ProjectList {
  return { results: [launch], invitations_to_decide: [], can_create: true, ...overrides };
}

function show(initial: ProjectList, candidates: Candidate[] = [anna, vera]) {
  renderWithIntl(<ProjectsPanel initial={initial} departments={[sales]} candidates={candidates} />);
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

describe("ProjectsPanel", () => {
  it("creates a project for a managed department", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(Response.json(launch, { status: 201 }));
    show(list({ results: [] }));
    expect(screen.getByText("Проектов пока нет.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Название проекта"), "Запуск продукта");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByRole("region", { name: "Запуск продукта" })).toBeInTheDocument();
    expect(lastCall()).toEqual({
      url: "/api/v1/projects",
      method: "POST",
      body: { name: "Запуск продукта", department_id: "d-sales" },
    });
  });

  it("adds an own employee at once", async () => {
    const user = userEvent.setup();
    const member = {
      user: { id: "u-anna", name: "Анна Петрова" },
      department: sales,
      is_active: true,
    };
    fetchMock.mockResolvedValueOnce(
      Response.json({ outcome: "added", project: { ...launch, members: [member] } }),
    );
    show(list());

    await user.selectOptions(screen.getByLabelText("Сотрудник"), "Анна Петрова");
    expect(screen.getByLabelText("Участвует от отдела")).toHaveValue("d-sales");
    await user.click(screen.getByRole("button", { name: "Добавить" }));

    expect(await screen.findByText("Анна Петрова — Продажи")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Сотрудник добавлен в проект.");
    expect(lastCall()).toEqual({
      url: "/api/v1/projects/p-1/members",
      method: "POST",
      body: { user_id: "u-anna", department_id: "d-sales" },
    });
    // Somebody who already takes part is not offered again.
    expect(
      within(screen.getByLabelText("Сотрудник")).queryByRole("option", { name: "Анна Петрова" }),
    ).toBeNull();
  });

  it("says that an employee of another department is only invited", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({
        outcome: "invited",
        project: { ...launch, pending_invitations: [veraInvitation] },
      }),
    );
    show(list());

    await user.selectOptions(screen.getByLabelText("Сотрудник"), "Вера Орлова");
    await user.click(screen.getByRole("button", { name: "Добавить" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Пока оно не согласовано, сотрудник в проекте не участвует.",
    );
    expect(screen.getByText("Вера Орлова — Поддержка")).toBeInTheDocument();
    expect(screen.getByText("Участников пока нет.")).toBeInTheDocument();
    expect(lastCall().body).toEqual({ user_id: "u-vera", department_id: "d-support" });
  });

  it("lets the employee's manager approve an invitation", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        Response.json(list({ results: [{ ...launch, can_manage: false }], can_create: true })),
      );
    show(list({ results: [], invitations_to_decide: [veraInvitation] }), []);
    const inbox = within(screen.getByRole("region", { name: "Приглашения вашим сотрудникам" }));
    expect(
      inbox.getByText(
        "Ольга Смирнова приглашает сотрудника Вера Орлова (отдел «Поддержка») в проект «Запуск продукта» отдела «Продажи».",
      ),
    ).toBeInTheDocument();

    await user.click(inbox.getByRole("button", { name: "Согласовать: Вера Орлова" }));

    expect(await screen.findByRole("region", { name: "Запуск продукта" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Приглашения вашим сотрудникам" })).toBeNull();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/project-invitations/i-1/approve");
    expect(init?.method).toBe("POST");
  });

  it("declines and withdraws invitations", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(Response.json(list({ results: [] })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(Response.json(list()));
    show(
      list({
        results: [{ ...launch, pending_invitations: [veraInvitation] }],
        invitations_to_decide: [{ ...veraInvitation, id: "i-2" }],
      }),
    );

    await user.click(screen.getByRole("button", { name: "Отклонить: Вера Орлова" }));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/project-invitations/i-2/decline");
    await screen.findByText("Проектов пока нет.");
  });

  it("is read-only for a participant", () => {
    const member = {
      user: { id: "u-anna", name: "Анна Петрова" },
      department: sales,
      is_active: true,
    };
    renderWithIntl(
      <ProjectsPanel
        initial={list({
          results: [{ ...launch, members: [member], can_manage: false }],
          can_create: false,
        })}
        departments={[]}
        candidates={[]}
      />,
    );

    expect(screen.getByText("Анна Петрова — Продажи")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByLabelText("Название проекта")).toBeNull();
  });

  it("explains a refusal", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code: "project_name_taken", message: "x" } }, { status: 400 }),
    );
    show(list());

    await user.type(
      screen.getByLabelText("Название проекта", {
        selector: "form[aria-label='Новый проект'] input",
      }),
      "Запуск продукта",
    );
    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Проект с таким названием уже есть.",
    );
  });
});
