import {
  API_PATHS,
  type CandidateList,
  type DepartmentList,
  type ProjectList,
} from "@crm/contracts";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { AppShell } from "@/components/app-shell";
import { ProjectsPanel } from "@/components/projects-panel";
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

export default async function ProjectsPage() {
  const t = await getTranslations("projects");
  const cookieHeader = (await cookies()).toString();
  const session = await fetchCurrentSession(cookieHeader);
  if (session.state === "anonymous") {
    redirect("/login");
  }
  const list =
    session.state === "authenticated"
      ? await fetchJson<ProjectList>(API_PATHS.projects, cookieHeader)
      : null;
  if (session.state !== "authenticated" || list === null) {
    notFound();
  }
  // Only somebody who runs projects needs (and may read) these two lists.
  const [departments, candidates] = list.can_create
    ? await Promise.all([
        fetchJson<DepartmentList>(API_PATHS.departments, cookieHeader),
        fetchJson<CandidateList>(API_PATHS.projectCandidates, cookieHeader),
      ])
    : [null, null];
  const managed = new Set(
    (departments?.results ?? [])
      .filter(
        (department) =>
          department.is_active &&
          department.managers.some((manager) => manager.id === session.me.user.id),
      )
      .map((department) => department.id),
  );

  return (
    <AppShell me={session.me} active="projects">
      <main className="mx-auto flex max-w-4xl flex-col gap-6 p-4">
        <h1 className="text-3xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("intro")}</p>
        <ProjectsPanel
          initial={list}
          departments={(departments?.results ?? [])
            .filter((department) => managed.has(department.id))
            .map(({ id, name }) => ({ id, name }))}
          candidates={candidates?.results ?? []}
        />
      </main>
    </AppShell>
  );
}
