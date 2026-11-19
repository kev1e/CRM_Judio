// Liveness of the web container itself; does not call the API.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
