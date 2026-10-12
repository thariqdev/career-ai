/**
 * Small helpers for job descriptions. No runtime imports, so tests/jobs.test.mjs can load
 * this file directly with Node.
 */

/** Same rule as the backend (normalize_text): ignore case and runs of spaces/new lines. */
export function sameText(a: string, b: string): boolean {
  const norm = (text: string) => text.split(/\s+/).filter(Boolean).join(" ").toLowerCase();
  return norm(a) !== "" && norm(a) === norm(b);
}

/** A job's name for lists: its title, else the start of its posting, else "Untitled job". */
export function jobLabel(job: { title: string | null; raw_text?: string }, length = 60): string {
  const title = job.title?.trim();
  if (title) return title;
  const text = (job.raw_text ?? "").split(/\s+/).filter(Boolean).join(" ");
  if (!text) return "Untitled job";
  return text.length <= length ? text : `${text.slice(0, length).trimEnd()}…`;
}

export type MatchBand = "strong" | "partial" | "low" | "none";

/** How well a job matches, in bands for the list's filter and badge. null = not compared yet. */
export function matchBand(percent: number | null): MatchBand {
  if (percent === null) return "none";
  if (percent >= 70) return "strong";
  if (percent >= 40) return "partial";
  return "low";
}

export const MATCH_FILTERS: { key: MatchBand | "any"; label: string }[] = [
  { key: "any", label: "Any match" },
  { key: "strong", label: "Strong · 70%+" },
  { key: "partial", label: "Partial · 40–69%" },
  { key: "low", label: "Low · under 40%" },
  { key: "none", label: "Not compared yet" },
];

export const MATCH_CLASSES: Record<MatchBand, string> = {
  strong: "bg-verified-bg text-verified",
  partial: "bg-partial-bg text-partial",
  low: "bg-not-verified-bg text-not-verified",
  none: "bg-ground text-ink-soft",
};

/**
 * A job's number, as the assistant uses it ("Untitled job #4 (pasted …)", backend
 * chunker.job_label since stage 80), so the list and the chat point at the same job.
 */
export function jobNumber(job: { id: number }): string {
  return `#${job.id}`;
}
