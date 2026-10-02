"use client";

import { useState } from "react";
import { apiPut, ApiError } from "@/lib/api";
import { PROGRESS_LABEL } from "@/lib/learning";
import { Card, Pill, SectionHeading } from "@/components/ui";
import type { LearningProgress, LearningProgressStatus } from "@/lib/types";

const OPTIONS: LearningProgressStatus[] = ["not_started", "studying", "finished"];

/**
 * Three buttons for the user's own learning progress on one skill. Progress is
 * never proof: when "finished" but the skill isn't verified, it says so and
 * points to evidence, rather than implying the skill is now known.
 */
export default function LearningProgressControl({
  skillId,
  status,
  verified,
  onChange,
}: {
  skillId: number;
  status: LearningProgressStatus;
  verified: boolean;
  onChange: (status: LearningProgressStatus) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose(next: LearningProgressStatus) {
    setError(null);
    setBusy(true);
    try {
      const saved = await apiPut<LearningProgress>(`/skills/${skillId}/learning-progress`, {
        status: next,
      });
      onChange(saved.status);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your progress.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeading title="Learning progress" hint="How far you are. Studying is never proof." />
      <div className="mt-3 flex flex-wrap gap-2">
        {OPTIONS.map((option) => (
          <Pill
            key={option}
            selected={status === option}
            disabled={busy}
            onClick={() => choose(option)}
          >
            {PROGRESS_LABEL[option]}
          </Pill>
        ))}
      </div>
      {status === "finished" && !verified && (
        <p className="mt-2 text-sm text-warm">
          Finished studying isn&apos;t proof yet. To get this skill verified, add evidence (like
          a project you built) and link it to your claim below.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-not-verified">{error}</p>}
    </Card>
  );
}
