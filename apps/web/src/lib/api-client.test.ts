import { describe, expect, it, vi } from "vitest";

import { callApi } from "./api-client";

describe("callApi", () => {
  it("sends JSON to this origin with the session cookie and returns the body", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ a: 1 }));

    const result = await callApi<{ a: number }>(
      "/api/v1/users",
      { method: "POST", body: { x: 1 } },
      fetchImpl,
    );

    expect(result).toEqual({ ok: true, data: { a: 1 } });
    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/users");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin", body: '{"x":1}' });
  });

  it("treats 204 as success without a body", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));

    await expect(callApi("/x", { method: "POST" }, fetchImpl)).resolves.toEqual({
      ok: true,
      data: undefined,
    });
  });

  it("returns the API's error code", async () => {
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        Response.json({ error: { code: "last_administrator", message: "x" } }, { status: 400 }),
      );

    await expect(callApi("/x", { method: "POST" }, fetchImpl)).resolves.toEqual({
      ok: false,
      code: "last_administrator",
    });
  });

  it.each([
    ["a foreign error body", () => Promise.resolve(new Response("Bad gateway", { status: 502 }))],
    ["a network failure", () => Promise.reject(new TypeError("offline"))],
  ])("is unavailable on %s", async (_name, behaviour) => {
    const fetchImpl = vi.fn<typeof fetch>().mockImplementation(behaviour);

    await expect(callApi("/x", { method: "GET" }, fetchImpl)).resolves.toEqual({
      ok: false,
      code: "unavailable",
    });
  });
});
