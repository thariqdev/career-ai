"use client";

import { useState } from "react";
import { apiPut, ApiError } from "@/lib/api";
import { PROGRESS_LABEL } from "@/lib/learning";
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
    <section className="mt-6">
      <h2 className="font-display text-lg text-ink">Learning progress</h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            disabled={busy}
            onClick={() => choose(option)}
            aria-pressed={status === option}
            className={`rounded border px-3 py-1.5 text-sm disabled:opacity-50 ${
              status === option
                ? "border-accent bg-accent-soft text-accent"
                : "border-line text-ink-soft"
            }`}
          >
            {PROGRESS_LABEL[option]}
          </button>
        ))}
      </div>
      {status === "finished" && !verified && (
        <p className="mt-2 text-sm text-warm">
          Finished studying isn&apos;t proof yet. To get this skill verified, add evidence (like
          a project you built) and link it to your claim below.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-not-verified">{error}</p>}
    </section>
  );
}
