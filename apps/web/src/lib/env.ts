/** Server-side environment, validated when it is first needed. */
export function getApiInternalUrl(source: NodeJS.ProcessEnv = process.env): URL {
  const raw = source.API_INTERNAL_URL;
  if (!raw) {
    throw new Error("API_INTERNAL_URL is not set (see .env.example).");
  }

  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("API_INTERNAL_URL is not a valid URL.");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("API_INTERNAL_URL must use http or https.");
  }
  return url;
}
