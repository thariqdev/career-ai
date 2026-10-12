"use client";

import StatusBadge from "@/components/StatusBadge";
import LearnLinks from "@/components/LearnLinks";
import StudyLinks from "@/components/StudyLinks";
import { cvBadgeClasses, cvBadgeLabel, useCvStatuses } from "@/lib/cv";
import { useLearningResources } from "@/lib/learning";
import type { Gap } from "@/lib/types";

/**
 * The gap list shared by the Dashboard and Job Descriptions pages: each gap's
 * requirement, status and skill, its current CV status (plus any CV advice), and
 * that skill's learning links. A gap not mapped to any skill gets neither, since
 * there's no skill to look up.
 *
 * Live since stage 89: the gaps are the skills the job asks for (the same as its match)
 * that you haven't proven yet, with your CURRENT status. A skill you haven't saved has no
 * saved links, so it gets YouTube search links instead.
 */
export default function GapList({ gaps }: { gaps: Gap[] }) {
  const learning = useLearningResources(
    gaps.flatMap((gap) => (gap.skill_id === null ? [] : [gap.skill_id])),
  );
  const cvStatuses = useCvStatuses();

  if (gaps.length === 0) {
    return (
      <p className="mt-3 rounded-md bg-verified-bg px-3 py-2 text-sm text-verified">
        No gaps: every skill this job asks for is verified.
      </p>
    );
  }

  return (
    <ul className="mt-3 flex flex-col gap-3">
      {gaps.map((gap) => {
        const skillId = gap.skill_id;
        const skillLearning = skillId === null ? undefined : learning[skillId];
        // Not in /cv/status means no claim and no CV mark, i.e. not on the CV.
        const cv = skillId === null ? undefined : cvStatuses[skillId];
        const cvStatus = cv?.cv_status ?? "not_present";
        return (
          <li
            key={gap.key}
            className="flex flex-col gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink"
          >
            <span className="flex flex-wrap items-center gap-3">
              <span className="font-medium">{gap.requirement_text}</span>
              <StatusBadge status={gap.status} />
              {skillId !== null && (
                <span className={`rounded px-2 py-0.5 font-mono text-xs ${cvBadgeClasses(cvStatus)}`}>
                  CV: {cvBadgeLabel(cvStatus)}
                </span>
              )}
              <span className="text-ink-soft">
                {gap.skill_name === null
                  ? "not mapped to a skill"
                  : skillId === null
                    ? `${gap.skill_name} · not in your skills yet`
                    : gap.skill_name}
              </span>
            </span>
            {cv?.recommendation && <span className="text-xs text-warm">{cv.recommendation}</span>}
            {skillLearning ? <LearnLinks learning={skillLearning} /> : skillId === null && <StudyLinks links={gap.study_links} />}
          </li>
        );
      })}
    </ul>
  );
}
