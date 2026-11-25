import { describe, expect, it, vi } from "vitest";

import { formatRemaining, logout, pollLogin, startLogin } from "./login-client";

function respondWith(status: number, body: unknown): typeof fetch {
  return vi.fn<typeof fetch>().mockResolvedValue(Response.json(body, { status }));
}

const failing: typeof fetch = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline"));

describe("startLogin", () => {
  it("posts the credentials to this origin and returns the deadline", async () => {
    const fetchImpl = respondWith(200, { expires_at: "2026-11-25T12:03:00Z", expires_in: 180 });

    const result = await startLogin("anna.petrova", " pass phrase ", fetchImpl);

    expect(result).toEqual({ ok: true, expiresAt: new Date("2026-11-25T12:03:00Z") });
    const [url, init] = vi.mocked(fetchImpl).mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/auth/login");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin" });
    // The password is sent exactly as typed.
    expect(JSON.parse(String(init?.body))).toEqual({
      login: "anna.petrova",
      password: " pass phrase ",
    });
  });

  it.each([
    [401, "invalid_credentials"],
    [409, "telegram_not_bound"],
  ] as const)("maps %s to %s", async (status, code) => {
    const fetchImpl = respondWith(status, { error: { code, message: "x", details: null } });

    await expect(startLogin("a", "b", fetchImpl)).resolves.toEqual({
      ok: false,
      failure: code,
      retryAfter: undefined,
    });
  });

  it("returns the wait when throttled", async () => {
    const fetchImpl = respondWith(429, {
      error: { code: "throttled", message: "x", details: { retry_after: 40 } },
    });

    await expect(startLogin("a", "b", fetchImpl)).resolves.toEqual({
      ok: false,
      failure: "throttled",
      retryAfter: 40,
    });
  });

  it.each([
    ["an unknown error code", respondWith(500, { error: { code: "internal_error" } })],
    ["a body that is not an error envelope", respondWith(502, "Bad gateway")],
    ["a network failure", failing],
  ])("is unavailable on %s", async (_name, fetchImpl) => {
    await expect(startLogin("a", "b", fetchImpl)).resolves.toEqual({
      ok: false,
      failure: "unavailable",
    });
  });
});

describe("pollLogin", () => {
  it.each([
    [{ state: "authenticated", delivery: null }, { state: "authenticated" }],
    [{ state: "pending", delivery: "pending" }, { state: "waiting" }],
    [{ state: "pending", delivery: "sent" }, { state: "waiting" }],
    [
      { state: "pending", delivery: "failed" },
      { state: "failed", failure: "delivery_failed" },
    ],
    [
      { state: "denied", delivery: null },
      { state: "failed", failure: "denied" },
    ],
    [
      { state: "expired", delivery: null },
      { state: "failed", failure: "expired" },
    ],
    [
      { state: "invalid", delivery: null },
      { state: "failed", failure: "invalid" },
    ],
    [{ state: "something-new", delivery: null }, { state: "retry" }],
  ])("maps %j to %j", async (body, expected) => {
    await expect(pollLogin(respondWith(200, body))).resolves.toEqual(expected);
  });

  it("posts without a body: the attempt is identified by an HttpOnly cookie", async () => {
    const fetchImpl = respondWith(200, { state: "pending", delivery: "sent" });

    await pollLogin(fetchImpl);

    const [url, init] = vi.mocked(fetchImpl).mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/auth/login/complete");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeUndefined();
  });

  it("keeps waiting through a server or network hiccup", async () => {
    await expect(pollLogin(respondWith(502, {}))).resolves.toEqual({ state: "retry" });
    await expect(pollLogin(failing)).resolves.toEqual({ state: "retry" });
  });
});

describe("logout", () => {
  it("posts to the logout endpoint and never throws", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));

    await logout(fetchImpl);
    await expect(logout(failing)).resolves.toBeUndefined();

    expect(vi.mocked(fetchImpl).mock.calls[0]?.[0]).toBe("/api/v1/auth/logout");
  });
});

describe("formatRemaining", () => {
  it.each([
    [180, "3:00"],
    [61.2, "1:02"],
    [9, "0:09"],
    [0, "0:00"],
    [-5, "0:00"],
  ])("%s seconds -> %s", (seconds, text) => {
    expect(formatRemaining(seconds)).toBe(text);
  });
});
