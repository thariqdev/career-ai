/**
 * Builds an .ics calendar file (RFC 5545) for one interview, so it can be added to any
 * calendar app. Pure functions with no runtime imports, so tests/calendar.test.mjs can
 * load this file directly with Node.
 *
 * Rules followed from the standard: CRLF line endings; times in UTC ("Z"), so every
 * calendar shows them in the user's own zone; commas, semicolons, backslashes and
 * new lines in text are escaped; lines longer than 75 bytes are folded (continued on
 * the next line after a single space).
 */

export type InterviewEvent = {
  jobId: number;
  title: string | null;
  company: string | null;
  at: Date; // when the interview starts
  notes: string | null;
  prepUrl: string; // link back to the job's interview prep sheet
  now: Date; // when the file is made (DTSTAMP)
};

const DURATION_MINUTES = 60; // the app stores only a start time
const EVENING_BEFORE_HOUR = 18; // reminder at 6 pm (local) the day before
const MAX_LINE_BYTES = 75;

/** 2026-10-06T04:00:00Z -> "20261006T040000Z" */
export function icsTime(at: Date): string {
  return at.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

/** Escape TEXT values: backslash first, then ; , and new lines. */
export function escapeText(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r\n|\r|\n/g, "\\n");
}

/** Fold one content line to at most 75 bytes per physical line, never splitting a character. */
export function foldLine(line: string): string[] {
  const encoder = new TextEncoder();
  const lines: string[] = [];
  let current = "";
  for (const char of line) {
    if (encoder.encode(current + char).length > MAX_LINE_BYTES) {
      lines.push(current);
      current = " " + char; // continuation lines start with one space
    } else {
      current += char;
    }
  }
  lines.push(current);
  return lines;
}

export function eventSummary(title: string | null, company: string | null): string {
  return `Interview: ${title ?? "Untitled job"}${company ? ` at ${company}` : ""}`;
}

/** "interview-backend-engineer-acme.ics" */
export function icsFileName(title: string | null, company: string | null): string {
  const slug = [title ?? "job", company ?? ""]
    .join(" ")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `interview-${slug || "job"}.ics`;
}

export function buildInterviewIcs(event: InterviewEvent): string {
  const end = new Date(event.at.getTime() + DURATION_MINUTES * 60 * 1000);
  const eveningBefore = new Date(
    event.at.getFullYear(),
    event.at.getMonth(),
    event.at.getDate() - 1,
    EVENING_BEFORE_HOUR,
  );
  const description = [event.notes?.trim(), `Interview prep sheet: ${event.prepUrl}`]
    .filter(Boolean)
    .join("\n\n");

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Career AI//Interview//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:career-ai-job-${event.jobId}-${icsTime(event.at)}@career-ai.local`,
    `DTSTAMP:${icsTime(event.now)}`,
    `DTSTART:${icsTime(event.at)}`,
    `DTEND:${icsTime(end)}`,
    `SUMMARY:${escapeText(eventSummary(event.title, event.company))}`,
    `DESCRIPTION:${escapeText(description)}`,
    `URL:${event.prepUrl}`,
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    `DESCRIPTION:${escapeText("Interview tomorrow: time to prep")}`,
    `TRIGGER;VALUE=DATE-TIME:${icsTime(eveningBefore)}`,
    "END:VALARM",
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    `DESCRIPTION:${escapeText("Interview in 1 hour")}`,
    "TRIGGER:-PT1H",
    "END:VALARM",
    "END:VEVENT",
    "END:VCALENDAR",
  ];
  return lines.flatMap(foldLine).join("\r\n") + "\r\n";
}
