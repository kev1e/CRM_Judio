import type { User } from "@crm/contracts";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { UsersPanel } from "./users-panel";

const fetchMock = vi.fn<typeof fetch>();

function account(overrides: Partial<User>): User {
  return {
    id: "u-1",
    crm_login: "anna.petrova",
    display_name: "Анна Петрова",
    responsibility: "",
    email: null,
    is_active: true,
    telegram_bound: true,
    has_password: true,
    created_at: "2026-11-25T10:00:00Z",
    departments: [],
    ...overrides,
  };
}

const admin = account({ id: "admin", crm_login: "root.admin", display_name: "Администратор" });
const anna = account({});
const newcomer = account({
  id: "u-2",
  crm_login: "ivan",
  display_name: "Иван Новиков",
  telegram_bound: false,
  has_password: false,
});
const ALL = { create: true, deactivate: true };

function renderPanel(users: User[], permissions = ALL) {
  return renderWithIntl(
    <UsersPanel initialUsers={users} permissions={permissions} currentUserId="admin" />,
  );
}

function row(name: string) {
  return within(screen.getByRole("row", { name: new RegExp(name) }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("UsersPanel", () => {
  it("lists accounts with what is still missing for each", () => {
    renderPanel([
      admin,
      anna,
      newcomer,
      account({ id: "u-3", display_name: "Олег", is_active: false }),
    ]);

    expect(row("Анна Петрова").getByText("Работает")).toBeInTheDocument();
    expect(row("Иван Новиков").getByText("Telegram не привязан")).toBeInTheDocument();
    expect(row("Иван Новиков").getByText("Пароль не задан")).toBeInTheDocument();
    expect(row("Олег").getByText("Отключён")).toBeInTheDocument();
  });

  it("offers only the actions that make sense for the account", () => {
    renderPanel([admin, anna, newcomer]);

    // Nobody deactivates themselves; a bound account gets no new binding code.
    expect(row("Администратор").queryByRole("button")).not.toBeInTheDocument();
    expect(row("Анна Петрова").queryByRole("button", { name: "Новый код привязки" })).toBeNull();
    expect(row("Иван Новиков").getByRole("button", { name: "Новый код привязки" })).toBeEnabled();
    expect(row("Анна Петрова").getByRole("button", { name: "Отключить" })).toBeEnabled();
  });

  it("hides what the viewer may not do", () => {
    renderPanel([admin, anna, newcomer], { create: false, deactivate: false });

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Логин")).not.toBeInTheDocument();
  });

  it("creates an account and shows the binding command once", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(
        Response.json(
          {
            user: newcomer,
            binding: {
              code: "CODE123",
              command: "/start CODE123",
              expires_at: "2026-11-25T10:30:00Z",
            },
          },
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(Response.json({ results: [admin, newcomer] }));
    renderPanel([admin]);

    await user.type(screen.getByLabelText("Имя и фамилия"), "Иван Новиков");
    await user.type(screen.getByLabelText(/^Логин/), "ivan");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    const code = await screen.findByRole("region", {
      name: /Код привязки Telegram для «Иван Новиков»/,
    });
    expect(within(code).getByText("/start CODE123")).toBeInTheDocument();
    expect(await screen.findByRole("row", { name: /Иван Новиков/ })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/users");
    expect(JSON.parse(String(init?.body))).toEqual({
      crm_login: "ivan",
      display_name: "Иван Новиков",
      email: null,
      department_id: null,
    });
    expect(screen.getByLabelText("Имя и фамилия")).toHaveValue("");

    await user.click(within(code).getByRole("button", { name: "Готово, код передан" }));
    expect(screen.queryByText("/start CODE123")).not.toBeInTheDocument();
  });

  it("explains why an account was not created", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code: "login_or_email_taken", message: "x" } }, { status: 400 }),
    );
    renderPanel([admin]);

    await user.type(screen.getByLabelText("Имя и фамилия"), "Иван");
    await user.type(screen.getByLabelText(/^Логин/), "root.admin");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Такой логин или email уже занят.");
    expect(screen.getByLabelText(/^Логин/)).toHaveValue("root.admin");
  });

  it("deactivates only after confirmation", async () => {
    const user = userEvent.setup();
    const confirm = vi
      .spyOn(window, "confirm")
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);
    fetchMock
      .mockResolvedValueOnce(Response.json({ ...anna, is_active: false }))
      .mockResolvedValueOnce(Response.json({ results: [admin, { ...anna, is_active: false }] }));
    renderPanel([admin, anna]);

    await user.click(row("Анна Петрова").getByRole("button", { name: "Отключить" }));
    expect(fetchMock).not.toHaveBeenCalled();

    await user.click(row("Анна Петрова").getByRole("button", { name: "Отключить" }));

    expect(
      await row("Анна Петрова").findByRole("button", { name: "Включить" }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/users/u-1/deactivate");
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Анна Петрова"));
  });

  it("shows a refusal from the server", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock
      .mockResolvedValueOnce(
        Response.json({ error: { code: "last_administrator", message: "x" } }, { status: 400 }),
      )
      .mockResolvedValueOnce(Response.json({ results: [admin, anna] }));
    renderPanel([admin, anna]);

    await user.click(row("Анна Петрова").getByRole("button", { name: "Отключить" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Нельзя отключить последнего администратора.",
    );
  });
});
