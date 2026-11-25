import { API_PATHS, type LoginProgress, type LoginStarted } from "@crm/contracts";

/** Why a sign-in step did not go through; keys of `login.errors` in the message catalogue. */
export type LoginFailure =
  | "invalid_credentials"
  | "throttled"
  | "telegram_not_bound"
  | "unavailable"
  | "delivery_failed"
  | "denied"
  | "expired"
  | "invalid";

export type StartResult =
  { ok: true; expiresAt: Date } | { ok: false; failure: LoginFailure; retryAfter?: number };

export type PollResult =
  | { state: "authenticated" }
  | { state: "waiting" }
  | { state: "failed"; failure: LoginFailure }
  // A hiccup between two polls: keep waiting, the next poll decides.
  | { state: "retry" };

const JSON_HEADERS = { Accept: "application/json", "Content-Type": "application/json" };
const KNOWN_START_FAILURES = new Set<string>([
  "invalid_credentials",
  "throttled",
  "telegram_not_bound",
]);

function errorOf(body: unknown): { code: string; retryAfter?: number } | null {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return null;
  }
  const error = body.error;
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  const details = "details" in error ? error.details : null;
  const retryAfter =
    typeof details === "object" &&
    details !== null &&
    "retry_after" in details &&
    typeof details.retry_after === "number"
      ? details.retry_after
      : undefined;
  return { code: String(error.code), retryAfter };
}

/** Step 1: send the login and password. The password is not kept anywhere afterwards. */
export async function startLogin(
  login: string,
  password: string,
  fetchImpl: typeof fetch = fetch,
): Promise<StartResult> {
  try {
    const response = await fetchImpl(API_PATHS.login, {
      method: "POST",
      headers: JSON_HEADERS,
      credentials: "same-origin",
      body: JSON.stringify({ login, password }),
    });
    const body: unknown = await response.json();
    if (response.ok) {
      const started = body as LoginStarted;
      return { ok: true, expiresAt: new Date(started.expires_at) };
    }
    const error = errorOf(body);
    if (error && KNOWN_START_FAILURES.has(error.code)) {
      return { ok: false, failure: error.code as LoginFailure, retryAfter: error.retryAfter };
    }
    return { ok: false, failure: "unavailable" };
  } catch {
    return { ok: false, failure: "unavailable" };
  }
}

/** Step 2: ask whether the attempt was approved in Telegram. */
export async function pollLogin(fetchImpl: typeof fetch = fetch): Promise<PollResult> {
  try {
    const response = await fetchImpl(API_PATHS.loginComplete, {
      method: "POST",
      headers: JSON_HEADERS,
      credentials: "same-origin",
    });
    if (!response.ok) {
      return { state: "retry" };
    }
    const progress = (await response.json()) as LoginProgress;
    switch (progress.state) {
      case "authenticated":
        return { state: "authenticated" };
      case "pending":
        return progress.delivery === "failed"
          ? { state: "failed", failure: "delivery_failed" }
          : { state: "waiting" };
      case "denied":
      case "expired":
      case "invalid":
        return { state: "failed", failure: progress.state };
      default:
        return { state: "retry" };
    }
  } catch {
    return { state: "retry" };
  }
}

export async function logout(fetchImpl: typeof fetch = fetch): Promise<void> {
  try {
    await fetchImpl(API_PATHS.logout, {
      method: "POST",
      headers: JSON_HEADERS,
      credentials: "same-origin",
    });
  } catch {
    // The caller leaves the page either way; a dead session cookie is refused by the API.
  }
}

export function formatRemaining(totalSeconds: number): string {
  const seconds = Math.max(0, Math.ceil(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
