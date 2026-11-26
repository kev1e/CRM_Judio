"use client";

import {
  API_PATHS,
  type Options,
  type RequestForm,
  type RequestFormList,
  type TaskCreated,
} from "@crm/contracts";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useState } from "react";

import { Modal } from "@/components/modal";
import { callApi, sendForm } from "@/lib/api-client";
import { type FormField } from "@/lib/form-fields";
import {
  emptyValues,
  type FormValue,
  type FormValues,
  toReason,
  toSubmission,
} from "@/lib/request-form";
import { fromLocalInput } from "@/lib/tasks";

const ERRORS = [
  "invalid_title",
  "assignee_not_eligible",
  "template_not_found",
  "template_changed",
  "unsupported_file_type",
  "file_too_large",
  "storage_unavailable",
  "permission_denied",
  "unavailable",
] as const;
type ErrorKey = (typeof ERRORS)[number];
type Failure = { kind: "general"; key: ErrorKey } | { kind: "field"; label: string; text: string };

const ACCEPT = ".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.webp,.zip";
const fieldClass =
  "h-11 w-full rounded-md border border-border bg-background px-3 text-base focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const labelClass = "flex flex-col gap-1 text-sm font-medium";

type Option = Options["results"][number];

function fieldsOf(form: RequestForm): FormField[] {
  return form.form_fields as unknown as FormField[];
}

export function NewRequestDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (created: TaskCreated) => void;
}) {
  const t = useTranslations("newRequest");
  const [forms, setForms] = useState<RequestForm[] | null>(null);
  const [formId, setFormId] = useState("");

  useEffect(() => {
    let active = true;
    void callApi<RequestFormList>(API_PATHS.requestForms, { method: "GET" }).then((result) => {
      if (!active) {
        return;
      }
      const list = result.ok ? result.data.results : [];
      setForms(list);
      setFormId(list[0]?.id ?? "");
    });
    return () => {
      active = false;
    };
  }, []);

  const form = forms?.find((candidate) => candidate.id === formId);

  return (
    <Modal labelledBy="new-request-title" onClose={onClose}>
      <h2 id="new-request-title" className="text-xl font-semibold">
        {t("title")}
      </h2>
      {forms === null ? (
        <p className="text-muted-foreground">{t("loading")}</p>
      ) : forms.length === 0 || !form ? (
        <>
          <p className="text-muted-foreground">{t("noForms")}</p>
          <button
            type="button"
            onClick={onClose}
            className="h-11 w-fit rounded-md border border-border px-4 hover:bg-muted"
          >
            {t("cancel")}
          </button>
        </>
      ) : (
        <>
          <label className={labelClass}>
            {t("formLabel")}
            <select
              value={formId}
              onChange={(event) => setFormId(event.target.value)}
              className={fieldClass}
            >
              {forms.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </option>
              ))}
            </select>
          </label>
          {form.description ? (
            <p className="text-sm text-muted-foreground">{form.description}</p>
          ) : null}
          {/* Another form starts from empty answers. */}
          <RequestFormBody key={form.id} form={form} onClose={onClose} onCreated={onCreated} />
        </>
      )}
    </Modal>
  );
}

function RequestFormBody({
  form,
  onClose,
  onCreated,
}: {
  form: RequestForm;
  onClose: () => void;
  onCreated: (created: TaskCreated) => void;
}) {
  const t = useTranslations("newRequest");
  const tTask = useTranslations("newTask");
  const tBoard = useTranslations("board");
  const fields = fieldsOf(form);
  const [departmentId, setDepartmentId] = useState(form.departments[0]?.id ?? "");
  const [people, setPeople] = useState<Option[]>([]);
  const [values, setValues] = useState<FormValues>(() => emptyValues(fields));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    if (!departmentId) {
      return;
    }
    let active = true;
    void callApi<Options>(`${API_PATHS.taskAssignees}?department_id=${departmentId}`, {
      method: "GET",
    }).then((result) => {
      if (active) {
        setPeople(result.ok ? result.data.results : []);
      }
    });
    return () => {
      active = false;
    };
  }, [departmentId]);

  function set(key: string, value: FormValue) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const submission = toSubmission(fields, values);
    const body = new FormData();
    body.append(
      "payload",
      JSON.stringify({
        template_id: form.id,
        version: form.version,
        department_id: departmentId,
        assignee_id: String(data.get("assignee_id") ?? ""),
        title: String(data.get("title") ?? ""),
        priority: String(data.get("priority") ?? "normal"),
        due_at: fromLocalInput(String(data.get("due_at") ?? "")),
        values: submission.values,
      }),
    );
    for (const [key, file] of submission.files) {
      body.append(`file.${key}`, file);
    }
    setBusy(true);
    setFailure(null);
    const result = await sendForm<TaskCreated>(API_PATHS.requests, body);
    setBusy(false);
    if (result.ok) {
      onCreated(result.data);
      return;
    }
    const refused = fields.find((field) => field.key === result.details?.field);
    if (refused && result.code === "invalid_form_value") {
      setFailure({
        kind: "field",
        label: refused.label,
        text: t(`reasons.${toReason(result.details?.reason)}`),
      });
    } else if (refused) {
      setFailure({ kind: "field", label: refused.label, text: t("reasons.badFile") });
    } else {
      setFailure({
        kind: "general",
        key: (ERRORS as readonly string[]).includes(result.code)
          ? (result.code as ErrorKey)
          : "unavailable",
      });
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
      {failure ? (
        <p role="alert" className="rounded-md border border-danger px-3 py-2 text-sm text-danger">
          {failure.kind === "field"
            ? t("fieldRefused", { label: failure.label, reason: failure.text })
            : t(`errors.${failure.key}`)}
        </p>
      ) : null}
      <label className={labelClass}>
        {tTask("titleLabel")}
        <input
          name="title"
          required
          maxLength={200}
          defaultValue={form.name}
          className={fieldClass}
        />
      </label>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          {tTask("departmentLabel")}
          <select
            value={departmentId}
            onChange={(event) => {
              setPeople([]);
              setDepartmentId(event.target.value);
              // People of another department cannot stay chosen.
              setValues((current) => {
                const next = { ...current };
                for (const field of fields) {
                  if (field.type === "employee") {
                    next[field.key] = "";
                  }
                }
                return next;
              });
            }}
            required
            className={fieldClass}
          >
            {form.departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          {tTask("assigneeLabel")}
          <select name="assignee_id" required defaultValue="" className={fieldClass}>
            <option value="" disabled>
              {people.length === 0 ? tTask("noAssignees") : tTask("chooseAssignee")}
            </option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.name}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          {tTask("priorityLabel")}
          <select name="priority" defaultValue="normal" className={fieldClass}>
            {(["low", "normal", "high", "urgent"] as const).map((priority) => (
              <option key={priority} value={priority}>
                {tBoard(`priority.${priority}`)}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          {tTask("dueLabel")}
          <input name="due_at" type="datetime-local" className={fieldClass} />
        </label>
      </div>

      {fields.length > 0 ? (
        <fieldset className="flex flex-col gap-4 rounded-md border border-border p-3">
          <legend className="px-1 text-sm font-medium">{t("formTitle")}</legend>
          {fields.map((field) => (
            <FieldInput
              key={field.key}
              field={field}
              value={values[field.key] ?? ""}
              people={people}
              onChange={(value) => set(field.key, value)}
            />
          ))}
        </fieldset>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={busy}
          className="h-11 rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90 disabled:opacity-60"
        >
          {busy ? t("submitting") : t("submit")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="h-11 rounded-md border border-border px-4 hover:bg-muted"
        >
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}

function FieldInput({
  field,
  value,
  people,
  onChange,
}: {
  field: FormField;
  value: FormValue;
  people: readonly Option[];
  onChange: (value: FormValue) => void;
}) {
  const t = useTranslations("newRequest");
  const text = typeof value === "string" ? value : "";
  const caption = (
    <>
      <span>
        {field.label}
        {field.required ? (
          <span aria-hidden="true" className="text-danger">
            {" "}
            *
          </span>
        ) : (
          <span className="font-normal text-muted-foreground"> {t("optional")}</span>
        )}
        {field.type === "number" && field.currency ? (
          <span className="font-normal text-muted-foreground">, {field.currency}</span>
        ) : null}
      </span>
      {field.help ? (
        <span className="text-xs font-normal text-muted-foreground">{field.help}</span>
      ) : null}
    </>
  );

  if (field.type === "select" && field.multiple) {
    const chosen = Array.isArray(value) ? value : [];
    return (
      <fieldset className="flex flex-col gap-1 text-sm font-medium">
        <legend className="flex flex-col gap-1">{caption}</legend>
        {(field.options ?? []).map((option) => (
          <label key={option} className="flex min-h-9 items-center gap-2 font-normal">
            <input
              type="checkbox"
              checked={chosen.includes(option)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...chosen, option]
                    : chosen.filter((item) => item !== option),
                )
              }
              className="size-4"
            />
            {option}
          </label>
        ))}
      </fieldset>
    );
  }

  let control;
  switch (field.type) {
    case "text":
      control = field.multiline ? (
        <textarea
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          maxLength={field.max_length}
          rows={3}
          className={`${fieldClass} h-auto py-2`}
        />
      ) : (
        <input
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          maxLength={field.max_length}
          className={fieldClass}
        />
      );
      break;
    case "reference":
      control = (
        <input
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          maxLength={200}
          className={fieldClass}
        />
      );
      break;
    case "number":
      control = (
        <input
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          inputMode={field.integer ? "numeric" : "decimal"}
          className={fieldClass}
        />
      );
      break;
    case "date":
      control = (
        <input
          type={field.with_time ? "datetime-local" : "date"}
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          className={fieldClass}
        />
      );
      break;
    case "select":
      control = (
        <select
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          className={fieldClass}
        >
          <option value="">{t("notChosen")}</option>
          {(field.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      );
      break;
    case "employee":
      control = (
        <select
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          className={fieldClass}
        >
          <option value="">{t("notChosen")}</option>
          {people.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name}
            </option>
          ))}
        </select>
      );
      break;
    case "boolean":
      control = (
        <select
          value={text}
          onChange={(event) => onChange(event.target.value)}
          required={field.required}
          className={fieldClass}
        >
          <option value="">{t("notChosen")}</option>
          <option value="true">{t("yes")}</option>
          <option value="false">{t("no")}</option>
        </select>
      );
      break;
    case "file":
      control = (
        <input
          type="file"
          accept={ACCEPT}
          onChange={(event) => onChange(event.target.files?.[0] ?? null)}
          className="text-sm font-normal file:mr-3 file:h-10 file:rounded-md file:border file:border-border file:bg-background file:px-3"
        />
      );
      break;
  }
  return (
    <label className={labelClass}>
      {caption}
      {control}
    </label>
  );
}
