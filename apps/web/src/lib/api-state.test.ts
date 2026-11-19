import { describe, expect, it, vi } from "vitest";

import { fetchApiState } from "./api-state";

const baseUrl = new URL("http://api.internal:8000");

function respondWith(status: number, body: unknown): typeof fetch {
  return vi.fn<typeof fetch>().mockResolvedValue(Response.json(body, { status }));
}

describe("fetchApiState", () => {
  it("calls the readiness endpoint of the internal API without caching", async () => {
    const fetchImpl = respondWith(200, { status: "ok", checks: { database: "ok", redis: "ok" } });

    await fetchApiState(fetchImpl, baseUrl);

    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = vi.mocked(fetchImpl).mock.calls[0] ?? [];
    expect(String(url)).toBe("http://api.internal:8000/api/v1/ready");
    expect(init).toMatchObject({ cache: "no-store" });
  });

  it("is ok when the API is ready", async () => {
    const fetchImpl = respondWith(200, { status: "ok", checks: { database: "ok", redis: "ok" } });

    await expect(fetchApiState(fetchImpl, baseUrl)).resolves.toBe("ok");
  });

  it("is degraded when the API answers 503", async () => {
    const fetchImpl = respondWith(503, {
      status: "unavailable",
      checks: { database: "fail", redis: "ok" },
    });

    await expect(fetchApiState(fetchImpl, baseUrl)).resolves.toBe("degraded");
  });

  it("is unreachable when the request fails", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed"));

    await expect(fetchApiState(fetchImpl, baseUrl)).resolves.toBe("unreachable");
  });

  it("is unreachable when the answer is not the readiness contract", async () => {
    const notJson = vi.fn<typeof fetch>().mockResolvedValue(new Response("<html>502</html>"));

    await expect(fetchApiState(notJson, baseUrl)).resolves.toBe("unreachable");
    await expect(fetchApiState(respondWith(200, { hello: "world" }), baseUrl)).resolves.toBe(
      "unreachable",
    );
  });
});
