import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { ApiStatus } from "@/components/api-status";
import { LogoutButton } from "@/components/logout-button";
import { ThemeToggle } from "@/components/theme-toggle";
import { fetchApiState } from "@/lib/api-state";
import { fetchCurrentSession } from "@/lib/session";

// The session and the API state are read on every request, never at build time.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const t = await getTranslations("home");
  const session = await fetchCurrentSession((await cookies()).toString());
  if (session.state === "anonymous") {
    redirect("/login");
  }
  const apiState = await fetchApiState();

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-6">
      <header className="flex items-center justify-between gap-2">
        <span className="text-lg font-semibold">{t("title")}</span>
        <div className="flex items-center gap-2">
          {session.state === "authenticated" ? <LogoutButton /> : null}
          <ThemeToggle />
        </div>
      </header>
      <main className="flex flex-1 flex-col justify-center gap-4 py-12">
        {session.state === "authenticated" ? (
          <>
            <h1 className="text-3xl font-semibold tracking-tight">
              {t("greeting", { name: session.me.user.display_name })}
            </h1>
            <p className="text-muted-foreground">{t("description")}</p>
          </>
        ) : (
          <h1 className="text-2xl font-semibold tracking-tight">{t("serverUnavailable")}</h1>
        )}
        <ApiStatus state={apiState} />
      </main>
    </div>
  );
}
