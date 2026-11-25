import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithIntl } from "@/test/render";

import { LoginForm } from "./login-form";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

const fetchMock = vi.fn<typeof fetch>();

function answer(status: number, body: unknown): Response {
  return Response.json(body, { status });
}

function started(seconds = 180): Response {
  return answer(200, {
    expires_at: new Date(Date.now() + seconds * 1000).toISOString(),
    expires_in: seconds,
  });
}

async function submitCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Логин"), "anna.petrova");
  await user.type(screen.getByLabelText("Пароль"), "plum-orbit-candle-73");
  await user.click(screen.getByRole("button", { name: "Войти" }));
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  replace.mockReset();
  refresh.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("LoginForm", () => {
  it("shows a labelled form with password-manager hints", () => {
    renderWithIntl(<LoginForm />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Вход в CRM");
    expect(screen.getByLabelText("Логин")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("autocomplete", "current-password");
  });

  it("never lets the browser put the password into the address", () => {
    // Without scripts the browser submits the form itself; GET would expose the password.
    renderWithIntl(<LoginForm />);

    expect(screen.getByLabelText("Пароль").closest("form")).toHaveAttribute("method", "post");
  });

  it("asks to confirm in Telegram and enters the CRM once approved", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    fetchMock
      .mockResolvedValueOnce(started())
      .mockResolvedValueOnce(answer(200, { state: "pending", delivery: "sent" }))
      .mockResolvedValueOnce(answer(200, { state: "authenticated", delivery: null }));
    renderWithIntl(<LoginForm />);

    await submitCredentials(user);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Подтвердите вход в Telegram" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent("Осталось 3:00");
    expect(screen.queryByLabelText("Пароль")).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(replace).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(2000));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(refresh).toHaveBeenCalled();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/auth/login",
      "/api/v1/auth/login/complete",
      "/api/v1/auth/login/complete",
    ]);
  });

  it.each([
    [401, { code: "invalid_credentials", details: null }, "Неверный логин или пароль."],
    [
      429,
      { code: "throttled", details: { retry_after: 40 } },
      "Слишком много попыток. Повторите через 40 с.",
    ],
    [
      409,
      { code: "telegram_not_bound", details: null },
      "Учётная запись ещё не привязана к Telegram. Попросите у администратора код привязки.",
    ],
    [500, { code: "internal_error", details: null }, "Не удалось связаться с сервером."],
  ])("explains a %s answer and keeps the form", async (status, error, text) => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    fetchMock.mockResolvedValueOnce(answer(status, { error: { ...error, message: "x" } }));
    renderWithIntl(<LoginForm />);

    await submitCredentials(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(text);
    expect(alert).toHaveFocus();
    expect(screen.getByRole("button", { name: "Войти" })).toBeEnabled();
    // The login stays for a retry; the password must be typed again.
    expect(screen.getByLabelText("Логин")).toHaveValue("anna.petrova");
    expect(screen.getByLabelText("Пароль")).toHaveValue("");
  });

  it.each([
    [{ state: "denied", delivery: null }, "Вход отклонён в Telegram."],
    [{ state: "expired", delivery: null }, "Время подтверждения истекло. Войдите ещё раз."],
    [
      { state: "pending", delivery: "failed" },
      "Не удалось отправить запрос в Telegram. Попробуйте войти позже.",
    ],
    [{ state: "invalid", delivery: null }, "Попытка входа больше не действительна."],
  ])("returns to the form when the attempt ends as %j", async (progress, text) => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    fetchMock.mockResolvedValueOnce(started()).mockResolvedValueOnce(answer(200, progress));
    renderWithIntl(<LoginForm />);
    await submitCredentials(user);
    await screen.findByRole("timer");

    await act(() => vi.advanceTimersByTimeAsync(2000));

    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(replace).not.toHaveBeenCalled();
  });

  it("stops waiting when the three minutes run out", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    fetchMock
      .mockResolvedValueOnce(started(3))
      .mockResolvedValue(answer(200, { state: "pending", delivery: "sent" }));
    renderWithIntl(<LoginForm />);
    await submitCredentials(user);
    await screen.findByRole("timer");

    await act(() => vi.advanceTimersByTimeAsync(4000));

    expect(await screen.findByRole("alert")).toHaveTextContent("Время подтверждения истекло.");
  });

  it("cancelling gives the attempt up on the server and stops polling", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    fetchMock
      .mockResolvedValueOnce(started())
      .mockResolvedValue(new Response(null, { status: 204 }));
    renderWithIntl(<LoginForm />);
    await submitCredentials(user);

    await user.click(await screen.findByRole("button", { name: "Отмена" }));

    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.at(-1)?.[0]).toBe("/api/v1/auth/logout");
    const callsAfterCancel = fetchMock.mock.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(fetchMock.mock.calls.length).toBe(callsAfterCancel);
  });

  it("keeps waiting through a temporary server error", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    fetchMock
      .mockResolvedValueOnce(started())
      .mockResolvedValueOnce(answer(502, { error: { code: "api_unreachable" } }))
      .mockResolvedValueOnce(answer(200, { state: "authenticated", delivery: null }));
    renderWithIntl(<LoginForm />);
    await submitCredentials(user);
    await screen.findByRole("timer");

    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(screen.getByRole("timer")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(2000));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
