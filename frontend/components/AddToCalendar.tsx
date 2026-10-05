"use client";

import { buildInterviewIcs, icsFileName } from "@/lib/calendar";
import { Button } from "@/components/ui";
import type { JobDescription } from "@/lib/types";

// Downloads the job's next interview as an .ics file any calendar app can open.
// Everything is built in the browser; nothing is sent anywhere.
export default function AddToCalendar({ job, size = "md" }: { job: JobDescription; size?: "sm" | "md" }) {
  if (job.next_interview_at === null) return null;
  const at = job.next_interview_at;

  function handleClick() {
    const ics = buildInterviewIcs({
      jobId: job.id,
      title: job.title,
      company: job.company,
      at: new Date(at),
      notes: job.application_notes,
      prepUrl: `${window.location.origin}/job-descriptions/${job.id}/prep`,
      now: new Date(),
    });
    const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = icsFileName(job.title, job.company);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <Button size={size} onClick={handleClick} title="Download an .ics file for your calendar app">
      📅 Add to calendar
    </Button>
  );
}
