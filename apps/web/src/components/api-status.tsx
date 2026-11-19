import { useTranslations } from "next-intl";

import type { ApiState } from "@/lib/api-state";

const dotClass: Record<ApiState, string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  unreachable: "bg-danger",
};

/** Shows only the overall state; which dependency failed stays on the server. */
export function ApiStatus({ state }: { state: ApiState }) {
  const t = useTranslations("apiStatus");

  return (
    <p
      role="status"
      aria-label={t("label")}
      data-state={state}
      className="inline-flex w-fit items-center gap-2 rounded-md border border-border bg-muted px-3 py-2 text-sm"
    >
      <span aria-hidden="true" className={`size-2.5 rounded-full ${dotClass[state]}`} />
      {t(state)}
    </p>
  );
}
