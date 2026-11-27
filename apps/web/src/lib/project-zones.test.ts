import type { Project } from "@crm/contracts";
import { describe, expect, it } from "vitest";

import { buildDiagram } from "./project-zones";

const sales = { id: "d-sales", name: "Продажи" };
const support = { id: "d-support", name: "Поддержка" };
const anna = { id: "u-anna", name: "Анна" };
const boris = { id: "u-boris", name: "Борис" };
const vera = { id: "u-vera", name: "Вера" };

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: "p-1",
    name: "Запуск",
    department: sales,
    is_active: true,
    members: [
      { user: anna, department: sales, is_active: true },
      { user: boris, department: sales, is_active: true },
      { user: vera, department: support, is_active: true },
    ],
    zones: [],
    pending_invitations: [],
    can_manage: true,
    ...overrides,
  };
}

describe("buildDiagram", () => {
  it("puts every participant into the circle of their department", () => {
    const diagram = buildDiagram(project());

    // The project's own department first.
    expect(diagram.departments.map((d) => d.name)).toEqual(["Продажи", "Поддержка"]);
    expect(diagram.regions.map((r) => [r.key, r.loose.map((p) => p.name)])).toEqual([
      ["d-sales", ["Анна", "Борис"]],
      ["d-support", ["Вера"]],
    ]);
  });

  it("puts a zone with people of two departments on the overlap", () => {
    const diagram = buildDiagram(
      project({
        zones: [
          { id: "z-1", name: "Договоры", members: [{ user: anna, is_responsible: true }] },
          {
            id: "z-2",
            name: "Запуск",
            members: [
              { user: vera, is_responsible: true },
              { user: boris, is_responsible: false },
            ],
          },
          { id: "z-3", name: "Пустая", members: [] },
        ],
      }),
    );

    const zonesOf = (key: string) =>
      diagram.regions.find((r) => r.key === key)?.zones.map((z) => z.name);
    // A zone nobody stands in yet belongs to the project's own department.
    expect(zonesOf("d-sales")).toEqual(["Договоры", "Пустая"]);
    expect(zonesOf("d-sales+d-support")).toEqual(["Запуск"]);
    // Whoever stands in a zone is not repeated among the people without one.
    expect(diagram.regions.flatMap((r) => r.loose)).toEqual([]);
  });

  it("shows a project without participants as its own department", () => {
    const diagram = buildDiagram(project({ members: [] }));

    expect(diagram.departments).toEqual([sales]);
    expect(diagram.regions).toHaveLength(1);
  });
});
