/** Browser-side calls to the CRM API through this origin. */

export type ApiResult<T> = { ok: true; data: T } | { ok: false; code: string };

const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };

function errorCode(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return null;
  }
  const error = body.error;
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  return typeof error.code === "string" ? error.code : null;
}

/**
 * Sends a request and returns either the parsed body or the API's stable error
 * code. Anything unexpected (network failure, a body that is not ours) is
 * reported as `unavailable`, never thrown.
 */
export async function callApi<T>(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown },
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResult<T>> {
  try {
    const response = await fetchImpl(path, {
      method: init.method,
      headers: JSON_HEADERS,
      credentials: "same-origin",
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
    if (response.status === 204) {
      return { ok: true, data: undefined as T };
    }
    const body: unknown = await response.json();
    if (response.ok) {
      return { ok: true, data: body as T };
    }
    return { ok: false, code: errorCode(body) ?? "unavailable" };
  } catch {
    return { ok: false, code: "unavailable" };
  }
}
