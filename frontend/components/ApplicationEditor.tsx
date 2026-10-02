"use client";

import { useState } from "react";
import { apiPatch, ApiError } from "@/lib/api";
import { APPLICATION_LABEL, APPLICATION_STATUSES, localToday } from "@/lib/applications";
import { Button, Pill, inputClasses } from "@/components/ui";
import type { ApplicationStatus, JobDescription } from "@/lib/types";

/**
 * Your application for this job: status, applied-on date and a note. The backend owns
 * the rules (no future date; "saved" has no date; "applied" with no date means today)
 * and its message is shown as-is. onSaved hands back the updated job.
 */
export default function ApplicationEditor({
  job,
  onSaved,
}: {
  job: JobDescription;
  onSaved: (job: JobDescription) => void;
}) {
  const [status, setStatus] = useState<ApplicationStatus>(job.application_status);
  const [appliedOn, setAppliedOn] = useState(job.applied_on ?? "");
  const [notes, setNotes] = useState(job.application_notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      // An empty date is left out (not sent as null), so "applied" fills in today.
      const body: Record<string, unknown> = { status, notes };
      if (appliedOn !== "") body.applied_on = appliedOn;
      else if (status === "saved" || job.applied_on !== null) body.applied_on = null;
      const updated = await apiPatch<JobDescription>(`/job-descriptions/${job.id}/application`, body);
      setStatus(updated.application_status);
      setAppliedOn(updated.applied_on ?? "");
      setNotes(updated.application_notes ?? "");
      setSaved(true);
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {APPLICATION_STATUSES.map((option) => (
          <Pill
            key={option}
            selected={status === option}
            onClick={() => {
              setStatus(option);
              setSaved(false);
              if (option === "saved") setAppliedOn("");
            }}
          >
            {APPLICATION_LABEL[option]}
          </Pill>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink-soft">
          Applied on
          <input
            type="date"
            value={appliedOn}
            max={localToday()}
            disabled={status === "saved"}
            onChange={(e) => {
              setAppliedOn(e.target.value);
              setSaved(false);
            }}
            className={`${inputClasses} disabled:opacity-50`}
          />
        </label>
        <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-sm text-ink-soft">
          Note
          <input
            value={notes}
            placeholder="e.g. Recruiter call Tues 3pm"
            onChange={(e) => {
              setNotes(e.target.value);
              setSaved(false);
            }}
            className={inputClasses}
          />
        </label>
        <Button variant="primary" onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
      {saved && <p className="text-sm text-verified">✓ Saved.</p>}
      {error && <p className="text-sm text-not-verified">{error}</p>}
    </div>
  );
}
