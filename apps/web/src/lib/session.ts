import "server-only";

import { API_PATHS, type Me } from "@crm/contracts";

import { getApiInternalUrl } from "./env";

const TIMEOUT_MS = 5000;

export type CurrentSession =
  { state: "authenticated"; me: Me } | { state: "anonymous" } | { state: "unavailable" };

function isMe(value: unknown): value is Me {
  return (
    typeof value === "object" &&
    value !== null &&
    "user" in value &&
    typeof value.user === "object" &&
    value.user !== null &&
    "display_name" in value.user &&
    typeof value.user.display_name === "string"
  );
}

/**
 * Asks the API who the request's cookies belong to. The answer is never cached
 * and never trusted from the browser: every page render asks again, so a revoked
 * session or a deactivated account loses the page at once.
 */
export async function fetchCurrentSession(
  cookieHeader: string,
  fetchImpl: typeof fetch = fetch,
  baseUrl: URL = getApiInternalUrl(),
): Promise<CurrentSession> {
  if (!cookieHeader) {
    return { state: "anonymous" };
  }
  try {
    const response = await fetchImpl(new URL(API_PATHS.me, baseUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      headers: { Accept: "application/json", Cookie: cookieHeader },
    });
    if (response.status === 401) {
      return { state: "anonymous" };
    }
    const body: unknown = await response.json();
    if (!response.ok || !isMe(body)) {
      return { state: "unavailable" };
    }
    return { state: "authenticated", me: body };
  } catch {
    return { state: "unavailable" };
  }
}
