"use client";

import StatusBadge from "@/components/StatusBadge";
import LearnLinks from "@/components/LearnLinks";
import { useLearningResources } from "@/lib/learning";
import type { Gap } from "@/lib/types";

/**
 * The gap list shared by the Dashboard and Job Descriptions pages: each gap's
 * requirement, status and skill, plus that skill's learning links. A gap not
 * mapped to any skill gets no links, since there is nothing to search for.
 */
export default function GapList({ gaps }: { gaps: Gap[] }) {
  const learning = useLearningResources(
    gaps.flatMap((gap) => (gap.requirement.skill_id === null ? [] : [gap.requirement.skill_id])),
  );

  if (gaps.length === 0) {
    return <p className="mt-2 text-ink-soft">No gaps — every requirement is verified.</p>;
  }

  return (
    <ul className="mt-3 flex flex-col gap-3">
      {gaps.map((gap) => {
        const skillId = gap.requirement.skill_id;
        const skillLearning = skillId === null ? undefined : learning[skillId];
        return (
          <li key={gap.requirement.id} className="flex flex-col gap-1 text-sm text-ink">
            <span className="flex items-center gap-3">
              <span>{gap.requirement.requirement_text}</span>
              <StatusBadge status={gap.result.knowledge_status} />
              <span className="text-ink-soft">
                {gap.requirement.skill_name ?? "not mapped to a skill"}
              </span>
            </span>
            {skillLearning && <LearnLinks learning={skillLearning} />}
          </li>
        );
      })}
    </ul>
  );
}
