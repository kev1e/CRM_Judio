import { API_PATHS, type Workflow } from "@crm/contracts";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/app-shell";
import { WorkflowPanel } from "@/components/workflow-panel";
import { getApiInternalUrl } from "@/lib/env";
import { fetchCurrentSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function fetchWorkflow(cookieHeader: string): Promise<Workflow | null> {
  try {
    const response = await fetch(new URL(API_PATHS.workflowStatuses, getApiInternalUrl()), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json", Cookie: cookieHeader },
    });
    return response.ok ? ((await response.json()) as Workflow) : null;
  } catch {
    return null;
  }
}

export default async function StatusesPage() {
  const t = await getTranslations("workflow");
  const cookieHeader = (await cookies()).toString();
  const session = await fetchCurrentSession(cookieHeader);
  if (session.state === "anonymous") {
    redirect("/login");
  }
  // The API decides who may configure statuses; for anybody else the page does not exist.
  const workflow = session.state === "authenticated" ? await fetchWorkflow(cookieHeader) : null;
  if (session.state !== "authenticated" || workflow === null) {
    notFound();
  }

  return (
    <AppShell me={session.me} active="workflow">
      <main className="mx-auto flex max-w-4xl flex-col gap-6 p-4">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("intro")}</p>
        <WorkflowPanel initialStatuses={workflow.results} />
      </main>
    </AppShell>
  );
}
