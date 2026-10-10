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
