import type { Project } from "@crm/contracts";

export type Named = { id: string; name: string };
export type ZonePerson = Named & { is_responsible: boolean };
export type DiagramZone = { id: string; name: string; people: ZonePerson[] };

/** One area of the picture: what belongs to exactly this set of departments. */
export type Region = {
  /** Sorted department ids joined with "+": the key of the area. */
  key: string;
  departments: Named[];
  zones: DiagramZone[];
  /** Participants from this department who stand in no zone (single departments only). */
  loose: Named[];
};

export type Diagram = { departments: Named[]; regions: Region[] };

/**
 * The project as overlapping departments (an Euler diagram).
 *
 * Nothing here is entered by hand: a participant stands in the circle of the
 * department they take part from; a zone lies in the circle of the department
 * its people come from, and on the overlap when they come from several.
 */
export function buildDiagram(project: Project): Diagram {
  const departmentOf = new Map(project.members.map((m) => [m.user.id, m.department]));
  const departments = new Map<string, Named>([[project.department.id, project.department]]);
  for (const member of project.members) {
    departments.set(member.department.id, member.department);
  }
  // The project's own department first, the others by name.
  const ordered = [...departments.values()].sort(
    (a, b) =>
      Number(b.id === project.department.id) - Number(a.id === project.department.id) ||
      a.name.localeCompare(b.name, "ru"),
  );
  const index = new Map(ordered.map((department, position) => [department.id, position]));

  const regions = new Map<string, Region>();
  function region(ids: string[]): Region {
    const sorted = [...new Set(ids)].sort((a, b) => (index.get(a) ?? 0) - (index.get(b) ?? 0));
    const key = sorted.join("+");
    let found = regions.get(key);
    if (!found) {
      found = {
        key,
        departments: sorted.flatMap((id) => departments.get(id) ?? []),
        zones: [],
        loose: [],
      };
      regions.set(key, found);
    }
    return found;
  }

  for (const department of ordered) {
    region([department.id]);
  }
  const placed = new Set<string>();
  for (const zone of project.zones) {
    const ids = zone.members.flatMap((m) => departmentOf.get(m.user.id)?.id ?? []);
    for (const member of zone.members) {
      placed.add(member.user.id);
    }
    // A zone nobody stands in yet belongs to the project's own department.
    region(ids.length > 0 ? ids : [project.department.id]).zones.push({
      id: zone.id,
      name: zone.name,
      people: zone.members.map((m) => ({ ...m.user, is_responsible: m.is_responsible })),
    });
  }
  for (const member of project.members) {
    if (!placed.has(member.user.id)) {
      region([member.department.id]).loose.push(member.user);
    }
  }
  return {
    departments: ordered,
    regions: [...regions.values()].sort(
      (a, b) => a.departments.length - b.departments.length || a.key.localeCompare(b.key),
    ),
  };
}
