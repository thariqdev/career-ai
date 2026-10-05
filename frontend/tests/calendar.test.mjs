// Checks for the interview .ics file (lib/calendar.ts), against RFC 5545's rules.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildInterviewIcs,
  escapeText,
  eventSummary,
  foldLine,
  icsFileName,
  icsTime,
} from "../lib/calendar.ts";

const AT = new Date("2026-10-06T04:00:00Z"); // 9:30 am in India
const NOW = new Date("2026-10-03T08:15:30Z");

function build(overrides = {}) {
  return buildInterviewIcs({
    jobId: 7,
    title: "Backend Engineer",
    company: "Acme",
    at: AT,
    notes: null,
    prepUrl: "http://localhost:3000/job-descriptions/7/prep",
    now: NOW,
    ...overrides,
  });
}

// Undo line folding, so content lines can be checked whole.
function unfolded(ics) {
  return ics.replace(/\r\n /g, "").split("\r\n");
}

test("the file has the required structure, CRLF endings and UTC times", () => {
  const ics = build();
  const lines = unfolded(ics);

  assert.ok(ics.endsWith("\r\n"));
  assert.ok(!/[^\r]\n/.test(ics), "every line ends with CRLF");
  assert.equal(lines[0], "BEGIN:VCALENDAR");
  assert.ok(lines.includes("VERSION:2.0"));
  assert.ok(lines.includes("DTSTART:20261006T040000Z"));
  assert.ok(lines.includes("DTEND:20261006T050000Z"));
  assert.ok(lines.includes("DTSTAMP:20261003T081530Z"));
  assert.ok(lines.includes("UID:career-ai-job-7-20261006T040000Z@career-ai.local"));
  assert.ok(lines.includes("SUMMARY:Interview: Backend Engineer at Acme"));
  assert.ok(lines.includes("URL:http://localhost:3000/job-descriptions/7/prep"));
  assert.equal(lines.filter((l) => l === "BEGIN:VEVENT").length, 1);
  assert.equal(lines.at(-2), "END:VCALENDAR");
});

test("two reminders: the evening before (6 pm local) and one hour before", () => {
  const lines = unfolded(build());
  const eveningBefore = new Date(AT.getFullYear(), AT.getMonth(), AT.getDate() - 1, 18);

  assert.equal(lines.filter((l) => l === "BEGIN:VALARM").length, 2);
  assert.ok(lines.includes(`TRIGGER;VALUE=DATE-TIME:${icsTime(eveningBefore)}`));
  assert.ok(lines.includes("TRIGGER:-PT1H"));
});

test("text is escaped so a title or note can't break the file", () => {
  assert.equal(escapeText("a,b;c\\d\ne"), "a\\,b\\;c\\\\d\\ne");

  const lines = unfolded(build({ title: "Dev, Ops; Lead", notes: "Room 4\nBring ID" }));

  assert.ok(lines.includes("SUMMARY:Interview: Dev\\, Ops\\; Lead at Acme"));
  const description = lines.find((l) => l.startsWith("DESCRIPTION:Room"));
  assert.equal(
    description,
    "DESCRIPTION:Room 4\\nBring ID\\n\\nInterview prep sheet: http://localhost:3000/job-descriptions/7/prep",
  );
});

test("long lines are folded at 75 bytes and unfold back exactly", () => {
  const long = "x".repeat(200);
  const folded = foldLine(`SUMMARY:${long}`);

  assert.ok(folded.every((l) => new TextEncoder().encode(l).length <= 75));
  assert.ok(folded.slice(1).every((l) => l.startsWith(" ")));
  assert.equal(folded.map((l, i) => (i === 0 ? l : l.slice(1))).join(""), `SUMMARY:${long}`);

  const ics = build({ notes: "é".repeat(100) }); // 2-byte characters are never split
  for (const line of ics.split("\r\n")) {
    assert.ok(new TextEncoder().encode(line).length <= 75, line);
  }
});

test("missing title or company still gives a sensible title and file name", () => {
  assert.equal(eventSummary(null, null), "Interview: Untitled job");
  assert.equal(eventSummary("Backend", null), "Interview: Backend");
  assert.equal(icsFileName("Backend Engineer", "Acme Ltd."), "interview-backend-engineer-acme-ltd.ics");
  assert.equal(icsFileName(null, null), "interview-job.ics");
});
