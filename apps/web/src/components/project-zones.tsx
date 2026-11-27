"use client";

import { API_PATHS, type Project } from "@crm/contracts";
import { useTranslations } from "next-intl";
import type { CSSProperties, FormEvent } from "react";

import { buildDiagram, type Diagram, type Named, type Region } from "@/lib/project-zones";

type Change = (
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: unknown,
) => Promise<boolean>;

// One colour per department, in the order the departments are drawn.
const COLORS = ["59 130 246", "34 197 94", "245 158 11", "168 85 247", "236 72 153", "20 184 166"];

function circle(position: number): CSSProperties {
  const rgb = COLORS[position % COLORS.length];
  return { backgroundColor: `rgb(${rgb} / 0.12)`, borderColor: `rgb(${rgb} / 0.9)` };
}

const chipClass = "rounded-md border border-border bg-card px-2 py-1 text-xs font-medium";
const fieldClass =
  "h-9 rounded-md border border-border bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const buttonClass =
  "h-9 rounded-md border border-border px-3 text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60";

// Where each area of three overlapping circles has its middle, in percent.
const THREE: Record<string, [number, number]> = {
  "0": [21, 24],
  "1": [79, 24],
  "2": [50, 84],
  "0+1": [50, 19],
  "0+2": [30, 57],
  "1+2": [70, 57],
  "0+1+2": [50, 43],
};

/**
 * The map of a project: circles are departments, people stand in the circle of
 * the department they take part from, zones of responsibility lie inside the
 * circles and on their overlaps. Drawn from the project's participants, so a new
 * project has it from the start and a new participant appears in it at once.
 */
export function ProjectZones({
  project,
  editable,
  busy,
  change,
}: {
  project: Project;
  /** The viewer runs the project and it is open. */
  editable: boolean;
  busy: boolean;
  change: Change;
}) {
  const t = useTranslations("projects.zones");
  const diagram = buildDiagram(project);
  const base = `${API_PATHS.projects}/${project.id}/zones`;
  const position = new Map(diagram.departments.map((d, at) => [d.id, at]));

  function label(region: Region): string {
    return region.departments.map((d) => d.name).join(" + ");
  }

  function content(region: Region, withTitle: boolean) {
    return (
      <div
        role="group"
        aria-label={label(region)}
        className="flex flex-col items-center gap-2 text-center"
      >
        {withTitle ? <span className="text-sm font-semibold">{label(region)}</span> : null}
        {region.zones.map((zone) => (
          <div
            key={zone.id}
            role="group"
            aria-label={`${t("zone")}: ${zone.name}`}
            className="flex flex-col items-center gap-1 rounded-2xl border border-dashed border-muted-foreground px-3 py-2"
          >
            <span className="text-xs text-muted-foreground">{zone.name}</span>
            <div className="flex flex-wrap justify-center gap-1">
              {zone.people.length === 0 ? (
                <span className="text-xs text-muted-foreground">{t("emptyZone")}</span>
              ) : (
                zone.people.map((one) => (
                  <span
                    key={one.id}
                    title={one.is_responsible ? t("responsible") : undefined}
                    className={
                      one.is_responsible
                        ? "rounded-md border border-primary bg-primary px-2 py-1 text-xs font-medium text-primary-foreground"
                        : chipClass
                    }
                  >
                    {one.name}
                    {one.is_responsible ? (
                      <span className="sr-only"> ({t("responsible")})</span>
                    ) : null}
                  </span>
                ))
              )}
            </div>
          </div>
        ))}
        {region.loose.length > 0 ? (
          <div className="flex flex-col items-center gap-1">
            {region.zones.length > 0 ? (
              <span className="text-xs text-muted-foreground">{t("noZone")}</span>
            ) : null}
            <div className="flex flex-wrap justify-center gap-1">
              {region.loose.map((one) => (
                <span key={one.id} className={chipClass}>
                  {one.name}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function byKey(departments: Named[]): Region | undefined {
    const key = departments.map((d) => d.id).join("+");
    return diagram.regions.find((region) => region.key === key);
  }

  function picture(shown: Diagram) {
    const [first, second, third] = shown.departments;
    if (first && !second) {
      const only = byKey([first]);
      return (
        <div className="flex justify-center">
          <div
            className="flex min-h-56 min-w-80 items-center justify-center rounded-[50%] border px-16 py-12"
            style={circle(0)}
          >
            {only ? content(only, true) : null}
          </div>
        </div>
      );
    }
    if (first && second && !third) {
      const columns = [byKey([first]), byKey([first, second]), byKey([second])];
      return (
        <div className="relative grid min-h-72 min-w-[640px] grid-cols-3">
          <div
            className="absolute inset-y-0 left-0 w-[64%] rounded-[50%] border"
            style={circle(0)}
          />
          <div
            className="absolute inset-y-0 right-0 w-[64%] rounded-[50%] border"
            style={circle(1)}
          />
          {columns.map((region, at) => (
            <div
              key={at}
              className={`relative flex items-center justify-center py-14 ${at === 0 ? "pr-2 pl-12" : at === 2 ? "pr-12 pl-2" : "px-2"}`}
            >
              {region ? (
                content(region, at !== 1)
              ) : at === 1 ? (
                <span className="text-xs text-muted-foreground">{t("noShared")}</span>
              ) : null}
            </div>
          ))}
        </div>
      );
    }
    if (first && second && third && shown.departments.length === 3) {
      const size = 62;
      const corners: CSSProperties[] = [
        { left: 0, top: 0 },
        { right: 0, top: 0 },
        { left: `${(100 - size) / 2}%`, bottom: 0 },
      ];
      return (
        <div className="relative mx-auto aspect-square w-[760px]">
          {corners.map((corner, at) => (
            <div
              key={at}
              className="absolute rounded-full border"
              style={{ ...corner, width: `${size}%`, height: `${size}%`, ...circle(at) }}
            />
          ))}
          {shown.regions.map((region) => {
            const key = region.departments.map((d) => position.get(d.id)).join("+");
            const [x, y] = THREE[key] ?? [50, 50];
            return (
              <div
                key={region.key}
                className="absolute w-[24%] -translate-x-1/2 -translate-y-1/2"
                style={{ left: `${x}%`, top: `${y}%` }}
              >
                {content(region, region.departments.length === 1)}
              </div>
            );
          })}
        </div>
      );
    }
    // Four circles and more cannot overlap in every combination on a plane:
    // each department gets its own circle, shared zones are listed under them.
    const shared = shown.regions.filter((region) => region.departments.length > 1);
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap justify-center gap-4">
          {shown.departments.map((department, at) => {
            const own = byKey([department]);
            return (
              <div
                key={department.id}
                className="flex min-h-48 min-w-64 items-center justify-center rounded-[50%] border px-12 py-10"
                style={circle(at)}
              >
                {own ? content(own, true) : null}
              </div>
            );
          })}
        </div>
        {shared.length > 0 ? (
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">{t("shared")}</span>
            <div className="flex flex-wrap gap-3">
              {shared.map((region) => (
                <div key={region.key} className="rounded-md border border-border p-3">
                  {content(region, true)}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  function submit(event: FormEvent<HTMLFormElement>, send: (data: FormData) => Promise<boolean>) {
    event.preventDefault();
    const form = event.currentTarget;
    void send(new FormData(form)).then((ok) => {
      if (ok) {
        form.reset();
      }
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-medium">{t("title")}</h3>
      <div className="overflow-x-auto pb-2">{picture(diagram)}</div>
      <p className="text-xs text-muted-foreground">{t("hint")}</p>

      {editable ? (
        <div className="flex flex-col gap-3">
          {project.zones.map((zone) => {
            const inside = new Set(zone.members.map((member) => member.user.id));
            const free = project.members.filter((member) => !inside.has(member.user.id));
            return (
              <fieldset
                key={zone.id}
                className="flex flex-col gap-2 rounded-md border border-border p-3"
              >
                <legend className="px-1 text-sm font-medium">{zone.name}</legend>
                <ul className="flex flex-col gap-1 text-sm">
                  {zone.members.map((member) => (
                    <li key={member.user.id} className="flex flex-wrap items-center gap-2">
                      <span className="flex-1">{member.user.name}</span>
                      <button
                        type="button"
                        disabled={busy}
                        aria-pressed={member.is_responsible}
                        aria-label={`${t("responsible")}: ${member.user.name}, ${zone.name}`}
                        onClick={() =>
                          void change(`${base}/${zone.id}/members`, "POST", {
                            user_id: member.user.id,
                            is_responsible: !member.is_responsible,
                          })
                        }
                        className={`${buttonClass} ${member.is_responsible ? "border-primary bg-primary text-primary-foreground hover:opacity-90" : ""}`}
                      >
                        {t("responsible")}
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={`${t("takeOut")}: ${member.user.name}, ${zone.name}`}
                        onClick={() =>
                          void change(`${base}/${zone.id}/members/${member.user.id}`, "DELETE")
                        }
                        className={buttonClass}
                      >
                        {t("takeOut")}
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="flex flex-wrap gap-2">
                  {free.length > 0 ? (
                    <form
                      onSubmit={(event) =>
                        submit(event, (data) => {
                          const userId = String(data.get("user_id") ?? "");
                          return userId
                            ? change(`${base}/${zone.id}/members`, "POST", { user_id: userId })
                            : Promise.resolve(false);
                        })
                      }
                      className="flex gap-2"
                    >
                      <select
                        name="user_id"
                        defaultValue=""
                        aria-label={`${t("putInto")}: ${zone.name}`}
                        className={fieldClass}
                      >
                        <option value="">{t("putInto")}</option>
                        {free.map((member) => (
                          <option key={member.user.id} value={member.user.id}>
                            {member.user.name} — {member.department.name}
                          </option>
                        ))}
                      </select>
                      <button type="submit" disabled={busy} className={buttonClass}>
                        {t("add")}
                      </button>
                    </form>
                  ) : null}
                  <form
                    onSubmit={(event) =>
                      submit(event, (data) =>
                        change(`${base}/${zone.id}`, "PATCH", {
                          name: String(data.get("name") ?? ""),
                        }),
                      )
                    }
                    className="flex gap-2"
                  >
                    <input
                      name="name"
                      required
                      maxLength={150}
                      autoComplete="off"
                      placeholder={t("newName")}
                      aria-label={`${t("newName")}: ${zone.name}`}
                      className={fieldClass}
                    />
                    <button type="submit" disabled={busy} className={buttonClass}>
                      {t("rename")}
                    </button>
                  </form>
                  <button
                    type="button"
                    disabled={busy}
                    aria-label={`${t("delete")}: ${zone.name}`}
                    onClick={() => void change(`${base}/${zone.id}`, "DELETE")}
                    className={buttonClass}
                  >
                    {t("delete")}
                  </button>
                </div>
              </fieldset>
            );
          })}
          <form
            onSubmit={(event) =>
              submit(event, (data) =>
                change(base, "POST", { name: String(data.get("name") ?? "") }),
              )
            }
            className="flex flex-wrap gap-2"
          >
            <input
              name="name"
              required
              maxLength={150}
              autoComplete="off"
              placeholder={t("zoneName")}
              aria-label={`${t("zoneName")}: ${project.name}`}
              className={`${fieldClass} min-w-60 flex-1`}
            />
            <button type="submit" disabled={busy} className={buttonClass}>
              {t("addZone")}
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
