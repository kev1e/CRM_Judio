import "server-only";

import { getApiInternalUrl } from "./env";

/**
 * The browser talks only to this origin; `/api/v1/*` is relayed to the API over
 * the internal network. The relay adds nothing and decides nothing: sessions,
 * permissions and the origin check all live in the API.
 */

const TIMEOUT_MS = 15_000;
// A 100 MB file over a slow connection takes minutes.
const FILE_TIMEOUT_MS = 10 * 60_000;
// Q16: 100 MB per file, plus room for the multipart envelope. The API enforces
// the exact limit; this only avoids holding an obviously oversized body in memory.
const MAX_BODY_BYTES = 101 * 1024 * 1024;

// Only what the API needs. In particular no `Host`, no hop-by-hop headers and no
// `X-Forwarded-*`: this server cannot vouch for the client address, so the API
// must not be given one that the client could have written itself.
const REQUEST_HEADERS = [
  "accept",
  "accept-language",
  "content-type",
  "cookie",
  "origin",
  "user-agent",
] as const;

const RESPONSE_HEADERS = [
  "cache-control",
  "content-type",
  "retry-after",
  // Downloads: the API decides the file name and forbids rendering in place.
  "content-disposition",
  "content-length",
  "content-security-policy",
  "x-content-type-options",
] as const;

const SEGMENT = /^[A-Za-z0-9._~-]+$/;

function errorResponse(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message, details: null } }, { status });
}

export async function forwardToApi(
  request: Request,
  path: readonly string[],
  fetchImpl: typeof fetch = fetch,
  baseUrl: URL = getApiInternalUrl(),
): Promise<Response> {
  if (
    path.length === 0 ||
    path.some((part) => part === "." || part === ".." || !SEGMENT.test(part))
  ) {
    return errorResponse(404, "not_found", "Not found.");
  }

  const target = new URL(`/api/v1/${path.join("/")}`, baseUrl);
  target.search = new URL(request.url).search;

  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) {
      headers.set(name, value);
    }
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (hasBody && (!Number.isFinite(declared) || declared > MAX_BODY_BYTES)) {
    return errorResponse(413, "file_too_large", "The file is larger than 100 MB.");
  }
  const isFile = path.includes("attachments");
  let upstream: Response;
  try {
    upstream = await fetchImpl(target, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(isFile ? FILE_TIMEOUT_MS : TIMEOUT_MS),
    });
  } catch {
    return errorResponse(502, "api_unreachable", "The server is not available.");
  }

  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) {
      responseHeaders.set(name, value);
    }
  }
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }

  const noBody = upstream.status === 204 || upstream.status === 304;
  return new Response(noBody ? null : upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
