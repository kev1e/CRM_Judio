import { API_PATHS, type StatusList, type TaskList } from "@crm/contracts";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { ApiStatus } from "@/components/api-status";
import { AppShell } from "@/components/app-shell";
import { TaskBoard } from "@/components/task-board";
import { fetchApiState } from "@/lib/api-state";
import { getApiInternalUrl } from "@/lib/env";
import { fetchCurrentSession } from "@/lib/session";
import { toBoardView } from "@/lib/tasks";

// The session and the tasks are read on every request, never at build time.
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

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ view?: string; task?: string }>;
}) {
  const t = await getTranslations("home");
  const cookieHeader = (await cookies()).toString();
  const session = await fetchCurrentSession(cookieHeader);
  if (session.state === "anonymous") {
    redirect("/login");
  }
  if (session.state === "unavailable") {
    return (
      <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-4 px-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("serverUnavailable")}</h1>
        <ApiStatus state={await fetchApiState()} />
      </main>
    );
  }

  const params = await searchParams;
  const view = toBoardView(params.view);
  // The API returns only what this viewer may see; the page adds nothing to that.
  const [statuses, tasks] = await Promise.all([
    fetchJson<StatusList>(API_PATHS.taskStatuses, cookieHeader),
    fetchJson<TaskList>(`${API_PATHS.tasks}?view=${view}`, cookieHeader),
  ]);

  return (
    <AppShell me={session.me} active={view}>
      <TaskBoard
        key={view}
        view={view}
        statuses={statuses?.results ?? []}
        initialCards={tasks?.results ?? []}
        canCreate={Boolean(session.me.permissions["task.create"])}
        initialTaskId={params.task && UUID.test(params.task) ? params.task : undefined}
      />
    </AppShell>
  );
}
