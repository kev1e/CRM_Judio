import "server-only";

import { API_PATHS, type Readiness } from "@crm/contracts";

import { getApiInternalUrl } from "./env";

export type ApiState = "ok" | "degraded" | "unreachable";

const TIMEOUT_MS = 3000;

function isReadiness(value: unknown): value is Readiness {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    (value.status === "ok" || value.status === "unavailable")
  );
}

/**
 * Asks the API whether it is ready. Runs on the server only: the browser never
 * learns the internal API address or which dependency is failing.
 */
export async function fetchApiState(
  fetchImpl: typeof fetch = fetch,
  baseUrl: URL = getApiInternalUrl(),
): Promise<ApiState> {
  try {
    const response = await fetchImpl(new URL(API_PATHS.ready, baseUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { Accept: "application/json" },
    });
    const body: unknown = await response.json();
    if (!isReadiness(body)) {
      return "unreachable";
    }
    return response.ok && body.status === "ok" ? "ok" : "degraded";
  } catch {
    return "unreachable";
  }
}
