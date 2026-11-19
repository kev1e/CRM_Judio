import { getTranslations } from "next-intl/server";

import { ApiStatus } from "@/components/api-status";
import { ThemeToggle } from "@/components/theme-toggle";
import { fetchApiState } from "@/lib/api-state";

// The API state is read on every request, never at build time.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const t = await getTranslations("home");
  const apiState = await fetchApiState();

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 py-6">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold">{t("title")}</span>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 flex-col justify-center gap-4 py-12">
        <h1 className="text-3xl font-semibold tracking-tight">{t("subtitle")}</h1>
        <p className="text-muted-foreground">{t("description")}</p>
        <ApiStatus state={apiState} />
      </main>
    </div>
  );
}
