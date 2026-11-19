// Public surface of the API contract. Everything here is generated from the
// OpenAPI schema exported by apps/api.
export type * from "./generated/types.gen";

/** Paths of the endpoints, kept next to their types so callers do not hard-code strings. */
export const API_PATHS = {
  health: "/api/v1/health",
  ready: "/api/v1/ready",
} as const satisfies Record<string, `/api/v${number}/${string}`>;
