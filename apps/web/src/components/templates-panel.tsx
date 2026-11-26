"use client";

import { API_PATHS, type Template } from "@crm/contracts";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";

import { callApi } from "@/lib/api-client";
import {
  FIELD_TYPES,
  type FieldType,
  type FormField,
  linesOf,
  newField,
  toNumberOrNull,
  toPayload,
  withType,
} from "@/lib/form-fields";

const ERROR_KEYS = [
  "invalid_template",
  "invalid_template_name",
  "template_name_taken",
  "template_not_found",
  "template_retired",
  "nothing_to_publish",
  "department_not_found",
  "validation_error",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERROR_KEYS)[number];

function toErrorKey(code: string): ErrorKey {
  return (ERROR_KEYS as readonly string[]).includes(code) ? (code as ErrorKey) : "unavailable";
}

type Option = { id: string; name: string };
type Draft = {
  id: string;
  name: string;
  description: string;
  departmentIds: Set<string>;
  fields: FormField[];
  checkpoints: string;
};
type Notice = { kind: "saved" } | { kind: "published"; number: number };

const fieldClass =
  "h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-9 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const primaryClass =
  "h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";
const checkClass = "flex items-center gap-2 text-sm";

function toDraft(template: Template): Draft {
  return {
    id: template.id,
    name: template.name,
    description: template.description,
    departmentIds: new Set(template.departments.map((department) => department.id)),
    fields: template.draft_fields as FormField[],
    checkpoints: template.draft_checkpoints.join("\n"),
  };
}

export function TemplatesPanel({
  initialTemplates,
  departments,
}: {
  initialTemplates: Template[];
  /** Open departments a template can be made available in. */
  departments: Option[];
}) {
  const t = useTranslations("templates");
  const format = useFormatter();
  const [templates, setTemplates] = useState(initialTemplates);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [addType, setAddType] = useState<FieldType>("text");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const createRef = useRef<HTMLFormElement>(null);

  async function change(
    path: string,
    method: "POST" | "PATCH",
    body?: unknown,
  ): Promise<Template | null> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await callApi<Template>(path, { method, body });
      if (!result.ok) {
        setError(toErrorKey(result.code));
        return null;
      }
      const updated = result.data;
      setTemplates((current) =>
        current.some((item) => item.id === updated.id)
          ? current.map((item) => (item.id === updated.id ? updated : item))
          : [...current, updated].sort((a, b) => a.name.localeCompare(b.name, "ru")),
      );
      return updated;
    } finally {
      setBusy(false);
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "");
    void change(API_PATHS.requestTemplates, "POST", { name }).then((created) => {
      if (created) {
        createRef.current?.reset();
        setDraft(toDraft(created));
      }
    });
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft) {
      return;
    }
    void change(`${API_PATHS.requestTemplates}/${draft.id}`, "PATCH", {
      name: draft.name,
      description: draft.description,
      department_ids: [...draft.departmentIds],
      draft_fields: draft.fields.map(toPayload),
      draft_checkpoints: linesOf(draft.checkpoints),
    }).then((saved) => {
      if (saved) {
        setDraft(null);
        setNotice({ kind: "saved" });
      }
    });
  }

  function publish(template: Template) {
    if (!window.confirm(t("confirmPublish", { name: template.name }))) {
      return;
    }
    void change(`${API_PATHS.requestTemplates}/${template.id}/publish`, "POST").then(
      (published) => {
        const number = published?.versions[0]?.number;
        if (number !== undefined) {
          setNotice({ kind: "published", number });
        }
      },
    );
  }

  function setField(index: number, patch: Partial<FormField>) {
    setDraft((current) =>
      current
        ? {
            ...current,
            fields: current.fields.map((field, at) =>
              at === index ? { ...field, ...patch } : field,
            ),
          }
        : current,
    );
  }

  function moveField(index: number, step: -1 | 1) {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const fields = [...current.fields];
      const moved = fields[index];
      const other = fields[index + step];
      if (!moved || !other) {
        return current;
      }
      fields[index] = other;
      fields[index + step] = moved;
      return { ...current, fields };
    });
  }

  function stateOf(template: Template): string {
    const number = template.versions[0]?.number;
    if (!template.is_active) {
      return t("stateRetired");
    }
    if (number === undefined) {
      return t("stateDraft");
    }
    return template.has_unpublished_changes
      ? t("stateChanged", { number })
      : t("statePublished", { number });
  }

  return (
    <div className="flex flex-col gap-8">
      {error ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {t(`errors.${error}`)}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="rounded-md border border-border px-3 py-2 text-sm">
          {notice.kind === "saved" ? t("saved") : t("published", { number: notice.number })}
        </p>
      ) : null}

      {draft ? (
        <form
          onSubmit={save}
          aria-label={t("editorTitle", { name: draft.name })}
          className="flex flex-col gap-6 rounded-md border border-border p-4"
        >
          <h2 className="text-lg font-semibold">{t("editorTitle", { name: draft.name })}</h2>
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("nameLabel")}
            <input
              required
              maxLength={150}
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              autoComplete="off"
              className={fieldClass}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("descriptionLabel")}
            <input
              maxLength={500}
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              autoComplete="off"
              className={fieldClass}
            />
          </label>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-sm font-medium">{t("departmentsTitle")}</legend>
            {departments.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noDepartments")}</p>
            ) : (
              <div className="flex flex-wrap gap-x-5 gap-y-2">
                {departments.map((department) => (
                  <label key={department.id} className={checkClass}>
                    <input
                      type="checkbox"
                      checked={draft.departmentIds.has(department.id)}
                      onChange={(event) => {
                        const next = new Set(draft.departmentIds);
                        if (event.target.checked) {
                          next.add(department.id);
                        } else {
                          next.delete(department.id);
                        }
                        setDraft({ ...draft, departmentIds: next });
                      }}
                    />
                    {department.name}
                  </label>
                ))}
              </div>
            )}
            <p className="text-xs text-muted-foreground">{t("departmentsHint")}</p>
          </fieldset>

          <div className="flex flex-col gap-3">
            <h3 className="text-sm font-medium">{t("fieldsTitle")}</h3>
            {draft.fields.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noFields")}</p>
            ) : null}
            {draft.fields.map((field, index) => (
              <fieldset
                key={field.key}
                className="flex flex-col gap-3 rounded-md border border-border p-3"
              >
                <legend className="px-1 text-sm font-medium">
                  {t("fieldHeading", { number: index + 1, label: field.label || t("untitled") })}
                </legend>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-1 text-sm font-medium">
                    {t("fieldLabel")}
                    <input
                      required
                      maxLength={120}
                      value={field.label}
                      onChange={(event) => setField(index, { label: event.target.value })}
                      autoComplete="off"
                      className={fieldClass}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-sm font-medium">
                    {t("fieldType")}
                    <select
                      value={field.type}
                      onChange={(event) =>
                        setField(index, withType(field, event.target.value as FieldType))
                      }
                      className={fieldClass}
                    >
                      {FIELD_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {t(`types.${type}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1 text-sm font-medium sm:col-span-2">
                    {t("fieldHelp")}
                    <input
                      maxLength={300}
                      value={field.help}
                      onChange={(event) => setField(index, { help: event.target.value })}
                      autoComplete="off"
                      className={fieldClass}
                    />
                  </label>
                </div>
                <div className="flex flex-wrap gap-x-5 gap-y-2">
                  <label className={checkClass}>
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={(event) => setField(index, { required: event.target.checked })}
                    />
                    {t("fieldRequired")}
                  </label>
                  {field.type === "text" ? (
                    <label className={checkClass}>
                      <input
                        type="checkbox"
                        checked={field.multiline ?? false}
                        onChange={(event) => setField(index, { multiline: event.target.checked })}
                      />
                      {t("multiline")}
                    </label>
                  ) : null}
                  {field.type === "number" ? (
                    <label className={checkClass}>
                      <input
                        type="checkbox"
                        checked={field.integer ?? false}
                        onChange={(event) => setField(index, { integer: event.target.checked })}
                      />
                      {t("integer")}
                    </label>
                  ) : null}
                  {field.type === "date" ? (
                    <label className={checkClass}>
                      <input
                        type="checkbox"
                        checked={field.with_time ?? false}
                        onChange={(event) => setField(index, { with_time: event.target.checked })}
                      />
                      {t("withTime")}
                    </label>
                  ) : null}
                  {field.type === "select" ? (
                    <label className={checkClass}>
                      <input
                        type="checkbox"
                        checked={field.multiple ?? false}
                        onChange={(event) => setField(index, { multiple: event.target.checked })}
                      />
                      {t("multiple")}
                    </label>
                  ) : null}
                </div>
                {field.type === "number" ? (
                  <div className="grid gap-3 sm:grid-cols-3">
                    <label className="flex flex-col gap-1 text-sm font-medium">
                      {t("min")}
                      <input
                        inputMode="decimal"
                        defaultValue={field.min ?? ""}
                        onChange={(event) =>
                          setField(index, { min: toNumberOrNull(event.target.value) })
                        }
                        className={fieldClass}
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-sm font-medium">
                      {t("max")}
                      <input
                        inputMode="decimal"
                        defaultValue={field.max ?? ""}
                        onChange={(event) =>
                          setField(index, { max: toNumberOrNull(event.target.value) })
                        }
                        className={fieldClass}
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-sm font-medium">
                      {t("currency")}
                      <input
                        maxLength={3}
                        value={field.currency ?? ""}
                        onChange={(event) =>
                          setField(index, { currency: event.target.value.trim() || null })
                        }
                        autoComplete="off"
                        className={fieldClass}
                      />
                    </label>
                  </div>
                ) : null}
                {field.type === "select" ? (
                  <label className="flex flex-col gap-1 text-sm font-medium">
                    {t("options")}
                    <textarea
                      required
                      rows={4}
                      defaultValue={(field.options ?? []).join("\n")}
                      onChange={(event) =>
                        setField(index, { options: linesOf(event.target.value) })
                      }
                      className={`${fieldClass} h-auto py-2`}
                    />
                  </label>
                ) : null}
                <p className="text-xs text-muted-foreground">{t(`typeHints.${field.type}`)}</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={index === 0}
                    onClick={() => moveField(index, -1)}
                    className={buttonClass}
                  >
                    {t("moveUp")}
                  </button>
                  <button
                    type="button"
                    disabled={index === draft.fields.length - 1}
                    onClick={() => moveField(index, 1)}
                    className={buttonClass}
                  >
                    {t("moveDown")}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setDraft({
                        ...draft,
                        fields: draft.fields.filter((_, at) => at !== index),
                      })
                    }
                    className={buttonClass}
                  >
                    {t("removeField")}
                  </button>
                </div>
              </fieldset>
            ))}
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex min-w-60 flex-col gap-1 text-sm font-medium">
                {t("fieldType")}
                <select
                  value={addType}
                  onChange={(event) => setAddType(event.target.value as FieldType)}
                  className={fieldClass}
                >
                  {FIELD_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {t(`types.${type}`)} — {t(`typeHints.${type}`)}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={() =>
                  setDraft({ ...draft, fields: [...draft.fields, newField(addType, draft.fields)] })
                }
                className={buttonClass}
              >
                {t("addField")}
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("checkpointsTitle")}</h3>
            <textarea
              rows={3}
              aria-label={t("checkpointsLabel")}
              placeholder={t("checkpointsLabel")}
              value={draft.checkpoints}
              onChange={(event) => setDraft({ ...draft, checkpoints: event.target.value })}
              className={`${fieldClass} h-auto py-2`}
            />
            <p className="text-xs text-muted-foreground">{t("checkpointsHint")}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={busy} className={primaryClass}>
              {t("save")}
            </button>
            <button type="button" onClick={() => setDraft(null)} className={buttonClass}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : (
        <>
          <form
            ref={createRef}
            onSubmit={create}
            aria-label={t("addTitle")}
            className="flex flex-wrap items-end gap-3"
          >
            <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm font-medium">
              {t("nameLabel")}
              <input
                name="name"
                required
                maxLength={150}
                autoComplete="off"
                className={fieldClass}
              />
            </label>
            <button type="submit" disabled={busy} className={primaryClass}>
              {t("create")}
            </button>
          </form>

          {templates.length === 0 ? <p className="text-muted-foreground">{t("empty")}</p> : null}

          {templates.map((template) => (
            <section
              key={template.id}
              aria-labelledby={`template-${template.id}`}
              className="flex flex-col gap-3 rounded-md border border-border p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <h2 id={`template-${template.id}`} className="text-lg font-semibold">
                    {template.name}
                  </h2>
                  <p className="text-sm text-muted-foreground">{stateOf(template)}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setNotice(null);
                      setError(null);
                      setDraft(toDraft(template));
                    }}
                    className={buttonClass}
                  >
                    {t("edit")}
                  </button>
                  {template.is_active &&
                  (template.has_unpublished_changes || template.versions.length === 0) ? (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => publish(template)}
                      className={primaryClass}
                    >
                      {t("publish")}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void change(`${API_PATHS.requestTemplates}/${template.id}`, "PATCH", {
                        is_active: !template.is_active,
                      })
                    }
                    className={buttonClass}
                  >
                    {t(template.is_active ? "retire" : "restore")}
                  </button>
                </div>
              </div>
              {template.description ? <p className="text-sm">{template.description}</p> : null}
              <p className="text-sm">
                {template.departments.length === 0
                  ? t("departmentsNone")
                  : t("departmentsList", {
                      names: template.departments.map((department) => department.name).join(", "),
                    })}
              </p>
              <p className="text-sm text-muted-foreground">
                {t("fieldCount", { count: template.draft_fields.length })}
              </p>
              {template.versions.length > 0 ? (
                <details>
                  <summary className="cursor-pointer text-sm font-medium">
                    {t("versionsTitle")}
                  </summary>
                  <ul className="mt-2 flex flex-col gap-1 text-sm">
                    {template.versions.map((version) => (
                      <li key={version.number}>
                        {t("versionItem", {
                          number: version.number,
                          date: format.dateTime(new Date(version.published_at), {
                            dateStyle: "medium",
                            timeStyle: "short",
                          }),
                          author: version.published_by,
                          count: version.form_fields.length,
                        })}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
