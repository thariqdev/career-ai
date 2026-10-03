// Checks for upcoming interviews and their countdown wording (lib/interviews.ts).
// Dates are built in local time, so these hold in any time zone.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clockTime,
  countdown,
  fromLocalInput,
  shortDateTime,
  toLocalInput,
  upcomingInterviews,
} from "../lib/interviews.ts";

// Friday 2 October 2026, 10:00 local time.
const NOW = new Date(2026, 9, 2, 10, 0);

function job(id, at) {
  return { id, title: `Job ${id}`, next_interview_at: at === null ? null : at.toISOString() };
}

test("only interviews from now to 14 days ahead, soonest first", () => {
  const jobs = [
    job(1, new Date(2026, 9, 10, 9, 0)), // in 8 days
    job(2, new Date(2026, 9, 2, 15, 0)), // later today
    job(3, new Date(2026, 9, 1, 9, 0)), // yesterday: past
    job(4, new Date(2026, 9, 2, 9, 59)), // a minute ago: past
    job(5, new Date(2026, 9, 17, 9, 0)), // 15 days: too far
    job(6, null), // no interview
  ];

  const ids = upcomingInterviews(jobs, NOW).map((u) => u.job.id);

  assert.deepEqual(ids, [2, 1]);
});

test("exactly now and exactly 14 days ahead are both included", () => {
  const jobs = [job(1, new Date(NOW)), job(2, new Date(NOW.getTime() + 14 * 24 * 60 * 60 * 1000))];

  assert.deepEqual(upcomingInterviews(jobs, NOW).map((u) => u.job.id), [1, 2]);
});

test("countdown wording by calendar day", () => {
  assert.equal(countdown(new Date(2026, 9, 2, 15, 0), NOW), "today at 3:00 pm");
  assert.equal(countdown(new Date(2026, 9, 3, 9, 30), NOW), "tomorrow at 9:30 am");
  assert.equal(countdown(new Date(2026, 9, 7, 9, 0), NOW), "in 5 days");
});

test("clock and date wording don't depend on the browser's locale", () => {
  assert.equal(clockTime(new Date(2026, 9, 2, 0, 5)), "12:05 am");
  assert.equal(clockTime(new Date(2026, 9, 2, 12, 0)), "12:00 pm");
  assert.equal(shortDateTime(new Date(2026, 9, 5, 9, 30)), "Mon 5 Oct, 9:30 am");
});

test("datetime-local values round-trip through the API's UTC form", () => {
  const iso = fromLocalInput("2026-10-06T09:30");
  assert.equal(toLocalInput(iso), "2026-10-06T09:30");
  assert.equal(fromLocalInput(""), null);
  assert.equal(toLocalInput(null), "");
});
