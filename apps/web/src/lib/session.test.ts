import { describe, expect, it, vi } from "vitest";

import { fetchCurrentSession } from "./session";

const baseUrl = new URL("http://api.internal:8000");
const me = {
  user: { id: "019ab3c4-0000-7000-8000-000000000001", crm_login: "anna", display_name: "Анна" },
  session: { expires_at: "2026-11-26T00:00:00Z" },
  permissions: {},
};

function respondWith(status: number, body: unknown): typeof fetch {
  return vi.fn<typeof fetch>().mockResolvedValue(Response.json(body, { status }));
}

describe("fetchCurrentSession", () => {
  it("is anonymous without cookies and does not call the API", async () => {
    const fetchImpl = respondWith(200, me);

    await expect(fetchCurrentSession("", fetchImpl, baseUrl)).resolves.toEqual({
      state: "anonymous",
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("forwards the cookies to the API and returns the user", async () => {
    const fetchImpl = respondWith(200, me);

    const session = await fetchCurrentSession("__Host-crm_session=abc", fetchImpl, baseUrl);

    expect(session).toEqual({ state: "authenticated", me });
    const [url, init] = vi.mocked(fetchImpl).mock.calls[0] ?? [];
    expect(String(url)).toBe("http://api.internal:8000/api/v1/auth/me");
    expect(init).toMatchObject({ cache: "no-store" });
    expect(new Headers(init?.headers).get("cookie")).toBe("__Host-crm_session=abc");
  });

  it("is anonymous when the API refuses the session", async () => {
    const fetchImpl = respondWith(401, { error: { code: "not_authenticated" } });

    await expect(fetchCurrentSession("x=1", fetchImpl, baseUrl)).resolves.toEqual({
      state: "anonymous",
    });
  });

  it.each([
    ["a server error", respondWith(500, { error: { code: "internal_error" } })],
    ["an unexpected body", respondWith(200, { hello: "world" })],
    ["a network failure", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("down"))],
  ])("is unavailable, not anonymous, on %s", async (_name, fetchImpl) => {
    // An outage must not look like "signed out" and bounce people to the login page.
    await expect(fetchCurrentSession("x=1", fetchImpl, baseUrl)).resolves.toEqual({
      state: "unavailable",
    });
  });
});
