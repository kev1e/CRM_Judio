import { describe, expect, it } from "vitest";

import { getApiInternalUrl } from "./env";

describe("getApiInternalUrl", () => {
  it("returns the configured URL", () => {
    const url = getApiInternalUrl({ API_INTERNAL_URL: "http://api:8000", NODE_ENV: "test" });

    expect(url.origin).toBe("http://api:8000");
  });

  it("fails when the variable is missing", () => {
    expect(() => getApiInternalUrl({ NODE_ENV: "test" })).toThrow("API_INTERNAL_URL is not set");
  });

  it.each(["not a url", "ftp://api:21", "file:///etc/passwd"])("rejects %s", (value) => {
    expect(() => getApiInternalUrl({ API_INTERNAL_URL: value, NODE_ENV: "test" })).toThrow(
      /API_INTERNAL_URL/,
    );
  });
});
