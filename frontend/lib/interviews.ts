/**
 * Upcoming interviews and their countdown wording. Pure functions with type-only
 * imports, so tests/interviews.test.mjs can load this file directly with Node.
 * All wording is in the user's own (local) time zone.
 */

import type { JobDescription } from "@/lib/types";

export const COMING_UP_DAYS = 14;

export type Upcoming = { job: JobDescription; at: Date };

/** Interviews from now to `days` days ahead, soonest first. Past ones are left out. */
export function upcomingInterviews(jobs: JobDescription[], now: Date, days = COMING_UP_DAYS): Upcoming[] {
  const end = now.getTime() + days * 24 * 60 * 60 * 1000;
  return jobs
    .filter((job) => job.next_interview_at !== null)
    .map((job) => ({ job, at: new Date(job.next_interview_at as string) }))
    .filter(({ at }) => at.getTime() >= now.getTime() && at.getTime() <= end)
    .sort((a, b) => a.at.getTime() - b.at.getTime());
}

/** "9:30 am", "3:05 pm": fixed wording, independent of the browser's locale settings. */
export function clockTime(at: Date): string {
  const hours = at.getHours();
  const minutes = String(at.getMinutes()).padStart(2, "0");
  return `${hours % 12 === 0 ? 12 : hours % 12}:${minutes} ${hours < 12 ? "am" : "pm"}`;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Mon 6 Oct, 9:30 am" */
export function shortDateTime(at: Date): string {
  return `${WEEKDAYS[at.getDay()]} ${at.getDate()} ${MONTHS[at.getMonth()]}, ${clockTime(at)}`;
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** "today at 3:00 pm", "tomorrow at 9:30 am", "in 5 days" (by calendar day, local time). */
export function countdown(at: Date, now: Date): string {
  const days = Math.round((startOfDay(at) - startOfDay(now)) / (24 * 60 * 60 * 1000));
  if (days <= 0) return `today at ${clockTime(at)}`;
  if (days === 1) return `tomorrow at ${clockTime(at)}`;
  return `in ${days} days`;
}

/** ISO time from the API -> the value a <input type="datetime-local"> shows (local time). */
export function toLocalInput(iso: string | null): string {
  if (iso === null) return "";
  const at = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

/** A datetime-local value (local time, no zone) -> ISO in UTC for the API; "" -> null. */
export function fromLocalInput(value: string): string | null {
  return value === "" ? null : new Date(value).toISOString();
}
