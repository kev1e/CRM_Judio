import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { resetCapturedToken, SetPasswordForm } from "./set-password-form";

const fetchMock = vi.fn<typeof fetch>();
const GOOD = "plum-orbit-candle-73";

async function fill(user: ReturnType<typeof userEvent.setup>, password: string, repeat: string) {
  await user.type(screen.getByLabelText(/^Новый пароль/), password);
  await user.type(screen.getByLabelText("Пароль ещё раз"), repeat);
  await user.click(screen.getByRole("button", { name: "Сохранить пароль" }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  resetCapturedToken();
  window.history.replaceState(null, "", "/set-password#one-time-token");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SetPasswordForm", () => {
  it("takes the token out of the address bar as soon as it is read", () => {
    renderWithIntl(<SetPasswordForm />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Пароль для входа в CRM");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/set-password");
  });

  it("saves the password with the token and points to the login page", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderWithIntl(<SetPasswordForm />);

    await fill(user, GOOD, GOOD);

    expect(await screen.findByRole("heading", { name: "Пароль сохранён" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Перейти ко входу" })).toHaveAttribute(
      "href",
      "/login",
    );
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/auth/password/setup");
    expect(JSON.parse(String(init?.body))).toEqual({ token: "one-time-token", password: GOOD });
  });

  it("does not call the server when the two passwords differ", async () => {
    const user = userEvent.setup();
    renderWithIntl(<SetPasswordForm />);

    await fill(user, GOOD, GOOD + "x");

    expect(await screen.findByRole("alert")).toHaveTextContent("Пароли не совпадают.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["invalid_password", "Пароль не подходит"],
    ["setup_link_rejected", "Ссылка больше не действует."],
    ["internal_error", "Не удалось связаться с сервером."],
  ])("explains the %s answer", async (code, text) => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      Response.json({ error: { code, message: "x", details: null } }, { status: 400 }),
    );
    renderWithIntl(<SetPasswordForm />);

    await fill(user, GOOD, GOOD);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(text);
    expect(alert).toHaveFocus();
  });

  it("uses fields a password manager recognises and never submits by GET", () => {
    renderWithIntl(<SetPasswordForm />);

    const field = screen.getByLabelText(/^Новый пароль/);
    expect(field).toHaveAttribute("autocomplete", "new-password");
    expect(field.closest("form")).toHaveAttribute("method", "post");
  });

  it("explains what to do when the page is opened without a link", () => {
    window.history.replaceState(null, "", "/set-password");
    renderWithIntl(<SetPasswordForm />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Ссылка недействительна");
    expect(screen.getByText(/команду \/password/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
