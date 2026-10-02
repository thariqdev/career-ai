import type { ApplicationStatus } from "@/lib/types";

/** Display order and labels for a job's application status (backend ApplicationStatus). */
export const APPLICATION_STATUSES: ApplicationStatus[] = [
  "saved",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

export const APPLICATION_LABEL: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

/** Tag colors, from the existing tokens: active ones in accent, good news green, closed grey. */
export const APPLICATION_CLASSES: Record<ApplicationStatus, string> = {
  saved: "bg-ground text-ink-soft",
  applied: "bg-accent-soft text-accent",
  interviewing: "bg-partial-bg text-partial",
  offer: "bg-verified-bg text-verified",
  rejected: "bg-not-verified-bg text-not-verified",
  withdrawn: "bg-provisional-bg text-provisional",
};

/** "Active" means still in play: applied or interviewing. */
export const ACTIVE_STATUSES: ApplicationStatus[] = ["applied", "interviewing"];
export const CLOSED_STATUSES: ApplicationStatus[] = ["rejected", "withdrawn"];

/** Today as YYYY-MM-DD in the user's own time zone (not UTC). */
export function localToday(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
