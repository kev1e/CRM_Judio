/** Browser-side calls to the CRM API through this origin. */

export type ApiResult<T> =
  | { ok: true; data: T }
  // `details` names what was refused (a field, a reason) — never data.
  | { ok: false; code: string; details?: Record<string, string> };

const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };

function errorDetails(body: unknown): Record<string, string> | undefined {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return undefined;
  }
  const error = body.error;
  if (typeof error !== "object" || error === null || !("details" in error)) {
    return undefined;
  }
  const details = error.details;
  if (typeof details !== "object" || details === null || Array.isArray(details)) {
    return undefined;
  }
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(details)) {
    if (typeof value === "string") {
      result[key] = value;
    }
  }
  return result;
}

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
  init: { method: "GET" | "POST" | "PATCH" | "DELETE"; body?: unknown },
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

/** Sends `multipart/form-data`; the browser sets the boundary itself. */
export async function sendForm<T>(
  path: string,
  form: FormData,
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResult<T>> {
  try {
    const response = await fetchImpl(path, {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      body: form,
    });
    const body: unknown = await response.json();
    if (response.ok) {
      return { ok: true, data: body as T };
    }
    return { ok: false, code: errorCode(body) ?? "unavailable", details: errorDetails(body) };
  } catch {
    return { ok: false, code: "unavailable" };
  }
}

/** Uploads one file as `multipart/form-data`. */
export async function uploadFile<T>(
  path: string,
  file: File,
  fetchImpl: typeof fetch = fetch,
): Promise<ApiResult<T>> {
  const form = new FormData();
  form.append("file", file);
  return sendForm<T>(path, form, fetchImpl);
}
