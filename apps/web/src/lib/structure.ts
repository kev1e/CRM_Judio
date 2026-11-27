import type { Department, User } from "@crm/contracts";

export type TreePerson = {
  id: string;
  display_name: string;
  crm_login: string;
  responsibility: string;
};

export type TreeManager = TreePerson & { is_designated: boolean };

export type DepartmentNode = {
  id: string;
  name: string;
  /** The designated manager first, then the others by name. */
  managers: TreeManager[];
  /** Members of the department who do not manage it. */
  employees: TreePerson[];
};

function byName(a: TreePerson, b: TreePerson): number {
  return a.display_name.localeCompare(b.display_name, "ru");
}

function person(source: TreePerson): TreePerson {
  const { id, display_name, crm_login, responsibility } = source;
  return { id, display_name, crm_login, responsibility };
}

/**
 * The company structure as it follows from the departments: open departments,
 * their managers and, under them, the employees. Nothing is stored separately,
 * so whoever is put into a department appears here by themselves.
 */
export function buildTree(departments: Department[]): DepartmentNode[] {
  return departments
    .filter((department) => department.is_active)
    .map((department) => {
      const managers = department.managers
        .filter((manager) => manager.is_active)
        .map((manager) => ({ ...person(manager), is_designated: manager.is_designated }))
        .sort((a, b) => Number(b.is_designated) - Number(a.is_designated) || byName(a, b));
      const managerIds = new Set(managers.map((manager) => manager.id));
      const employees = department.members
        .filter((member) => member.is_active && !managerIds.has(member.id))
        .map(person)
        .sort(byName);
      return { id: department.id, name: department.name, managers, employees };
    })
    .sort((a, b) => a.name.localeCompare(b.name, "ru"));
}

/** Active employees who are in no open department yet, neither as members nor as managers. */
export function withoutDepartment(departments: Department[], users: User[]): TreePerson[] {
  const placed = new Set<string>();
  for (const department of departments) {
    if (department.is_active) {
      for (const somebody of [...department.members, ...department.managers]) {
        placed.add(somebody.id);
      }
    }
  }
  return users
    .filter((user) => user.is_active && !placed.has(user.id))
    .map(person)
    .sort(byName);
}
