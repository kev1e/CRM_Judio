import { describe, expect, it, vi } from "vitest";

import { forwardToApi } from "./api-proxy";

const baseUrl = new URL("http://api.internal:8000");

function upstream(response: Response): typeof fetch {
  return vi.fn<typeof fetch>().mockResolvedValue(response);
}

function sent(fetchImpl: typeof fetch): { url: string; init: RequestInit; headers: Headers } {
  const [url, init] = vi.mocked(fetchImpl).mock.calls[0] ?? [];
  return { url: String(url), init: init ?? {}, headers: new Headers(init?.headers) };
}

describe("forwardToApi", () => {
  it("relays the method, path, query, body and the headers the API needs", async () => {
    const fetchImpl = upstream(Response.json({ ok: true }));
    const request = new Request("http://crm.local/api/v1/auth/login?x=1", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: "crm_login_attempt=abc",
        Origin: "http://crm.local",
        "User-Agent": "Browser/1",
      },
      body: JSON.stringify({ login: "anna" }),
    });

    const response = await forwardToApi(request, ["auth", "login"], fetchImpl, baseUrl);

    expect(response.status).toBe(200);
    const { url, init, headers } = sent(fetchImpl);
    expect(url).toBe("http://api.internal:8000/api/v1/auth/login?x=1");
    expect(init.method).toBe("POST");
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"login":"anna"}');
    expect(headers.get("cookie")).toBe("crm_login_attempt=abc");
    expect(headers.get("origin")).toBe("http://crm.local");
    expect(headers.get("user-agent")).toBe("Browser/1");
    expect(init.redirect).toBe("manual");
  });

  it("does not pass on addresses or internal headers supplied by the client", async () => {
    const fetchImpl = upstream(Response.json({}));
    const request = new Request("http://crm.local/api/v1/auth/me", {
      headers: {
        "X-Forwarded-For": "6.6.6.6",
        "X-Real-IP": "6.6.6.6",
        Forwarded: "for=6.6.6.6",
        Authorization: "Bearer x",
        "X-Internal": "1",
      },
    });

    await forwardToApi(request, ["auth", "me"], fetchImpl, baseUrl);

    const { headers, init } = sent(fetchImpl);
    expect([...headers.keys()]).toEqual([]);
    expect(init.body).toBeUndefined();
  });

  it("passes every Set-Cookie back unchanged", async () => {
    const headers = new Headers({
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    headers.append("Set-Cookie", "__Host-crm_session=s; HttpOnly; Secure; Path=/; SameSite=Lax");
    headers.append("Set-Cookie", "crm_login_attempt=; Max-Age=0; Path=/api/v1/auth/");
    headers.append("X-Internal-Detail", "secret");
    const fetchImpl = upstream(new Response("{}", { status: 200, headers }));
    const request = new Request("http://crm.local/api/v1/auth/login/complete", { method: "POST" });

    const response = await forwardToApi(request, ["auth", "login", "complete"], fetchImpl, baseUrl);

    expect(response.headers.getSetCookie()).toEqual([
      "__Host-crm_session=s; HttpOnly; Secure; Path=/; SameSite=Lax",
      "crm_login_attempt=; Max-Age=0; Path=/api/v1/auth/",
    ]);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("x-internal-detail")).toBeNull();
  });

  it("keeps the API's status, error body and Retry-After", async () => {
    const fetchImpl = upstream(
      Response.json(
        { error: { code: "throttled", message: "x", details: { retry_after: 9 } } },
        { status: 429, headers: { "Retry-After": "9" } },
      ),
    );
    const request = new Request("http://crm.local/api/v1/auth/login", { method: "POST" });

    const response = await forwardToApi(request, ["auth", "login"], fetchImpl, baseUrl);

    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("9");
    expect(await response.json()).toMatchObject({ error: { code: "throttled" } });
  });

  it("relays an empty 204", async () => {
    const fetchImpl = upstream(new Response(null, { status: 204 }));
    const request = new Request("http://crm.local/api/v1/auth/logout", { method: "POST" });

    const response = await forwardToApi(request, ["auth", "logout"], fetchImpl, baseUrl);

    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });

  it.each([[[]], [[".."]], [["auth", "..", "..", "admin"]], [["a b"]], [["%2e%2e"]], [["a/b"]]])(
    "refuses the path %j without calling the API",
    async (path) => {
      const fetchImpl = upstream(Response.json({}));
      const request = new Request("http://crm.local/api/v1/x");

      const response = await forwardToApi(request, path, fetchImpl, baseUrl);

      expect(response.status).toBe(404);
      expect(fetchImpl).not.toHaveBeenCalled();
    },
  );

  it("answers 502 in the error envelope when the API cannot be reached", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("ECONNREFUSED api"));
    const request = new Request("http://crm.local/api/v1/auth/me");

    const response = await forwardToApi(request, ["auth", "me"], fetchImpl, baseUrl);

    expect(response.status).toBe(502);
    const body = await response.text();
    expect(JSON.parse(body)).toEqual({
      error: { code: "api_unreachable", message: "The server is not available.", details: null },
    });
    // Nothing about the internal network leaks.
    expect(body).not.toContain("ECONNREFUSED");
    expect(body).not.toContain("api.internal");
  });
});
