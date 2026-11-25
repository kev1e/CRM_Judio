import { forwardToApi } from "@/lib/api-proxy";

// Every call depends on the caller's cookies: never cached, never prerendered.
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };

async function handle(request: Request, context: Context): Promise<Response> {
  const { path } = await context.params;
  return forwardToApi(request, path);
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };
