"use client";

import StatusBadge from "@/components/StatusBadge";
import LearnLinks from "@/components/LearnLinks";
import { cvBadgeClasses, cvBadgeLabel, useCvStatuses } from "@/lib/cv";
import { useLearningResources } from "@/lib/learning";
import type { Gap } from "@/lib/types";

/**
 * The gap list shared by the Dashboard and Job Descriptions pages: each gap's
 * requirement, status and skill, its current CV status (plus any CV advice), and
 * that skill's learning links. A gap not mapped to any skill gets neither, since
 * there's no skill to look up.
 *
 * The knowledge badge is the status from when this job was last compared; the CV
 * badge and advice are current (they come from GET /cv/status).
 */
export default function GapList({ gaps }: { gaps: Gap[] }) {
  const learning = useLearningResources(
    gaps.flatMap((gap) => (gap.requirement.skill_id === null ? [] : [gap.requirement.skill_id])),
  );
  const cvStatuses = useCvStatuses();

  if (gaps.length === 0) {
    return <p className="mt-2 text-ink-soft">No gaps — every requirement is verified.</p>;
  }

  return (
    <ul className="mt-3 flex flex-col gap-3">
      {gaps.map((gap) => {
        const skillId = gap.requirement.skill_id;
        const skillLearning = skillId === null ? undefined : learning[skillId];
        // Not in /cv/status means no claim and no CV mark, i.e. not on the CV.
        const cv = skillId === null ? undefined : cvStatuses[skillId];
        const cvStatus = cv?.cv_status ?? "not_present";
        return (
          <li key={gap.requirement.id} className="flex flex-col gap-1 text-sm text-ink">
            <span className="flex flex-wrap items-center gap-3">
              <span>{gap.requirement.requirement_text}</span>
              <StatusBadge status={gap.result.knowledge_status} />
              {skillId !== null && (
                <span className={`rounded px-2 py-0.5 font-mono text-xs ${cvBadgeClasses(cvStatus)}`}>
                  CV: {cvBadgeLabel(cvStatus)}
                </span>
              )}
              <span className="text-ink-soft">
                {gap.requirement.skill_name ?? "not mapped to a skill"}
              </span>
            </span>
            {cv?.recommendation && <span className="text-xs text-warm">{cv.recommendation}</span>}
            {skillLearning && <LearnLinks learning={skillLearning} />}
          </li>
        );
      })}
    </ul>
  );
}
