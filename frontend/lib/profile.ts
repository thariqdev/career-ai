import type { Education, Project, WorkExperience } from "@/lib/types";

// "2022-01-15" -> "Jan 2022". Parsed as parts, not new Date("2022-01-15"), which
// would be read as UTC midnight and can show the previous month in some time zones.
export function monthYear(isoDate: string): string {
  const [year, month] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
}

export function dateRange(start: string | null, end: string | null, ongoingLabel = "present"): string {
  if (!start && !end) return "";
  if (start && !end) return `${monthYear(start)} – ${ongoingLabel}`;
  if (!start && end) return `until ${monthYear(end)}`;
  return `${monthYear(start!)} – ${monthYear(end!)}`;
}

export function projectLabel(p: Project): string {
  return p.role ? `${p.name} (${p.role})` : p.name;
}

export function workLabel(w: WorkExperience): string {
  return `${w.role} at ${w.company}`;
}

export function educationLabel(e: Education): string {
  const what = [e.degree, e.field_of_study ? `in ${e.field_of_study}` : null].filter(Boolean).join(" ");
  return what ? `${what}, ${e.institution}` : e.institution;
}
