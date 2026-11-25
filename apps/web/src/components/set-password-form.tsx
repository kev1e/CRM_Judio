"use client";

import { API_PATHS } from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { callApi } from "@/lib/api-client";

type Failure = "mismatch" | "invalid_password" | "setup_link_rejected" | "unavailable";
type Phase = { name: "form"; failure?: Failure } | { name: "saving" } | { name: "done" };

const KNOWN: ReadonlySet<string> = new Set(["invalid_password", "setup_link_rejected"]);

// A second link opened in the same tab changes only the fragment: start over
// with a fresh page, so the new token is read and the old state is gone.
function subscribe(): () => void {
  const onHashChange = () => {
    if (window.location.hash.length > 1) {
      window.location.reload();
    }
  };
  window.addEventListener("hashchange", onHashChange);
  return () => window.removeEventListener("hashchange", onHashChange);
}

const fieldClass =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

// The one-time token arrives in the URL fragment, which the browser never sends
// to a server. It is read once and then removed from the address bar and history.
let capturedToken: string | null = null;
function readToken(): string {
  if (capturedToken === null) {
    capturedToken = window.location.hash.replace(/^#/, "");
    if (capturedToken) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }
  return capturedToken;
}

/** For tests: forget the token captured from a previous render. */
export function resetCapturedToken(): void {
  capturedToken = null;
}

export function SetPasswordForm() {
  const t = useTranslations("setPassword");
  const token = useSyncExternalStore(subscribe, readToken, () => null);
  const [phase, setPhase] = useState<Phase>({ name: "form" });
  const errorRef = useRef<HTMLParagraphElement>(null);

  const failure = phase.name === "form" ? phase.failure : undefined;
  useEffect(() => {
    if (failure) {
      errorRef.current?.focus();
    }
  }, [failure]);

  if (token === null) {
    return null; // before hydration: nothing to show yet
  }
  if (token === "") {
    return (
      <section className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("noLinkTitle")}</h1>
        <p className="text-muted-foreground">{t("noLinkDescription")}</p>
      </section>
    );
  }
  if (phase.name === "done") {
    return (
      <section className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("doneTitle")}</h1>
        <p className="text-muted-foreground">{t("doneDescription")}</p>
        {}
        <a
          href="/login"
          className="inline-flex h-11 w-fit items-center rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {t("toLogin")}
        </a>
      </section>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") ?? "");
    if (password !== String(data.get("repeat") ?? "")) {
      setPhase({ name: "form", failure: "mismatch" });
      return;
    }
    setPhase({ name: "saving" });
    const result = await callApi<void>(API_PATHS.passwordSetup, {
      method: "POST",
      body: { token, password },
    });
    if (result.ok) {
      setPhase({ name: "done" });
    } else {
      setPhase({
        name: "form",
        failure: KNOWN.has(result.code) ? (result.code as Failure) : "unavailable",
      });
    }
  }

  const saving = phase.name === "saving";
  return (
    <form
      method="post"
      action="/set-password"
      onSubmit={(event) => void submit(event)}
      className="flex flex-col gap-4"
      noValidate
    >
      <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
      <p className="text-muted-foreground">{t("description")}</p>
      {failure ? (
        <p
          ref={errorRef}
          role="alert"
          tabIndex={-1}
          className="rounded-md border border-danger px-3 py-2 text-sm text-danger"
        >
          {t(`errors.${failure}`)}
        </p>
      ) : null}
      <label className="flex flex-col gap-1 text-sm font-medium">
        {t("passwordLabel")}
        <input
          name="password"
          type="password"
          required
          minLength={12}
          maxLength={128}
          autoComplete="new-password"
          aria-describedby="password-hint"
          autoFocus
          readOnly={saving}
          className={fieldClass}
        />
        <span id="password-hint" className="font-normal text-muted-foreground">
          {t("hint")}
        </span>
      </label>
      <label className="flex flex-col gap-1 text-sm font-medium">
        {t("repeatLabel")}
        <input
          name="repeat"
          type="password"
          required
          maxLength={128}
          autoComplete="new-password"
          readOnly={saving}
          className={fieldClass}
        />
      </label>
      <button
        type="submit"
        disabled={saving}
        className="h-11 rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
      >
        {saving ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}
