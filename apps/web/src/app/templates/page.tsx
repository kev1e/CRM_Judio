import { API_PATHS, type DepartmentList, type TemplateList } from "@crm/contracts";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/app-shell";
import { TemplatesPanel } from "@/components/templates-panel";
import { getApiInternalUrl } from "@/lib/env";
import { fetchCurrentSession } from "@/lib/session";

export const dynamic = "force-dynamic";

async function fetchJson<T>(path: string, cookieHeader: string): Promise<T | null> {
  try {
    const response = await fetch(new URL(path, getApiInternalUrl()), {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
      headers: { Accept: "application/json", Cookie: cookieHeader },
    });
    return response.ok ? ((await response.json()) as T) : null;
  } catch {
    return null;
  }
}

export default async function TemplatesPage() {
  const t = await getTranslations("templates");
  const cookieHeader = (await cookies()).toString();
  const session = await fetchCurrentSession(cookieHeader);
  if (session.state === "anonymous") {
    redirect("/login");
  }
  // The API decides who may manage templates; for anybody else the page does not exist.
  const list =
    session.state === "authenticated"
      ? await fetchJson<TemplateList>(API_PATHS.requestTemplates, cookieHeader)
      : null;
  if (session.state !== "authenticated" || list === null) {
    notFound();
  }
  const departments = await fetchJson<DepartmentList>(API_PATHS.departments, cookieHeader);

  return (
    <AppShell me={session.me} active="templates">
      <main className="mx-auto flex max-w-4xl flex-col gap-6 p-4">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("intro")}</p>
        <TemplatesPanel
          initialTemplates={list.results}
          departments={(departments?.results ?? [])
            .filter((department) => department.is_active)
            .map(({ id, name }) => ({ id, name }))}
        />
      </main>
    </AppShell>
  );
}
