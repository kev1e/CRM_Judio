import type { Department, User } from "@crm/contracts";
import { describe, expect, it } from "vitest";

import { buildTree, withoutDepartment } from "./structure";

function somebody(id: string, name: string, extra: Partial<{ is_active: boolean }> = {}) {
  return {
    id,
    crm_login: id,
    display_name: name,
    responsibility: "",
    is_active: true,
    ...extra,
  };
}

const olga = somebody("olga", "Ольга");
const pavel = somebody("pavel", "Павел");
const anna = somebody("anna", "Анна");
const boris = somebody("boris", "Борис");
const gone = somebody("gone", "Яков", { is_active: false });

const sales: Department = {
  id: "d-sales",
  name: "Продажи",
  is_active: true,
  members: [
    { ...boris, is_primary: true },
    { ...anna, is_primary: true },
    { ...pavel, is_primary: true },
    { ...gone, is_primary: true },
  ],
  managers: [
    { ...olga, is_designated: false },
    { ...pavel, is_designated: true },
  ],
};
const closed: Department = {
  id: "d-old",
  name: "Архивный",
  is_active: false,
  members: [{ ...anna, is_primary: false }],
  managers: [],
};

function account(source: ReturnType<typeof somebody>): User {
  return {
    ...source,
    email: null,
    telegram_bound: true,
    has_password: true,
    created_at: "2026-11-01T00:00:00Z",
    departments: [],
  };
}

describe("buildTree", () => {
  it("puts the designated manager first and the employees under the managers", () => {
    const [node] = buildTree([sales]);

    expect(node?.managers.map((manager) => manager.display_name)).toEqual(["Павел", "Ольга"]);
    // A manager who is also a member is not repeated among the employees;
    // a deactivated account is not shown.
    expect(node?.employees.map((employee) => employee.display_name)).toEqual(["Анна", "Борис"]);
  });

  it("leaves closed departments out", () => {
    expect(buildTree([closed, sales]).map((node) => node.name)).toEqual(["Продажи"]);
  });
});

describe("withoutDepartment", () => {
  it("lists active employees who are in no open department", () => {
    const vera = somebody("vera", "Вера");
    const users = [olga, pavel, anna, boris, gone, vera].map(account);

    expect(withoutDepartment([sales, closed], users).map((one) => one.display_name)).toEqual([
      "Вера",
    ]);
  });
});
