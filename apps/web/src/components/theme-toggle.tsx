"use client";

import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const subscribe = () => () => undefined;

/** True only in the browser after hydration, so the server never renders a guessed theme. */
function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}

export function ThemeToggle() {
  const t = useTranslations("theme");
  const { resolvedTheme, setTheme } = useTheme();
  const hydrated = useHydrated();

  const isDark = hydrated && resolvedTheme === "dark";
  const label = isDark ? t("switchToLight") : t("switchToDark");

  return (
    <button
      type="button"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      disabled={!hydrated}
      aria-label={label}
      title={label}
      className="inline-flex size-10 items-center justify-center rounded-md border border-border text-lg hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <span aria-hidden="true">{isDark ? "☀" : "☾"}</span>
    </button>
  );
}
