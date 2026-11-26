"use client";

import { API_PATHS, type FormAnswer, type SubmittedForm, type TaskForm } from "@crm/contracts";
import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { callApi } from "@/lib/api-client";

/** What was typed into the form of a request. The API shows it only to those
 *  who may read the task. `revision` changes when the task's files change. */
export function TaskFormSection({ taskId, revision }: { taskId: string; revision: number }) {
  const t = useTranslations("taskForm");
  const [form, setForm] = useState<SubmittedForm | null>(null);

  useEffect(() => {
    let active = true;
    void callApi<TaskForm>(`${API_PATHS.tasks}/${taskId}/form`, { method: "GET" }).then(
      (result) => {
        if (active && result.ok) {
          setForm(result.data.form);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [taskId, revision]);

  if (!form) {
    return null;
  }
  return (
    <section aria-labelledby="task-form" className="flex flex-col gap-2">
      <h3 id="task-form" className="text-sm font-medium">
        {t("title", { name: form.template_name })}{" "}
        <span className="font-normal text-muted-foreground">
          {t("version", { number: form.version })}
        </span>
      </h3>
      {form.answers.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("noFields")}</p>
      ) : (
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[minmax(8rem,auto)_1fr]">
          {form.answers.map((answer) => (
            <div key={answer.key} className="contents">
              <dt className="text-muted-foreground">{answer.question}</dt>
              <dd className="mb-2 break-words whitespace-pre-wrap sm:mb-0">
                <AnswerValue taskId={taskId} answer={answer} />
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function AnswerValue({ taskId, answer }: { taskId: string; answer: FormAnswer }) {
  const t = useTranslations("taskForm");
  const format = useFormatter();
  const value = answer.value;
  if (!answer.filled) {
    return <span className="text-muted-foreground">{t("empty")}</span>;
  }
  if (answer.type === "file") {
    return answer.attachment_id && typeof value === "string" ? (
      <a
        href={`${API_PATHS.tasks}/${taskId}/attachments/${answer.attachment_id}`}
        className="underline underline-offset-2"
      >
        {value}
      </a>
    ) : (
      <span className="text-muted-foreground">{t("fileRemoved")}</span>
    );
  }
  if (answer.type === "boolean") {
    return value === true ? t("yes") : t("no");
  }
  if (Array.isArray(value)) {
    return value.map(String).join(", ");
  }
  if (typeof value !== "string") {
    return <span className="text-muted-foreground">{t("empty")}</span>;
  }
  if (answer.type === "date") {
    return answer.with_time
      ? format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" })
      : // A calendar date: shown as typed, whatever the reader's time zone.
        format.dateTime(new Date(`${value}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" });
  }
  if (answer.type === "number") {
    return answer.currency ? `${value} ${answer.currency}` : value;
  }
  return value;
}
