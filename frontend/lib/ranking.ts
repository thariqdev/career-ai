/**
 * Which skills to learn first, from your job gaps and where each application stands.
 * Deterministic: no AI, and nothing here is guessed about you.
 *
 * Kept free of runtime imports (types only), so the plain Node test in
 * tests/ranking.test.mjs can load it directly.
 */

import type { ApplicationStatus, Gap } from "@/lib/types";

/** Applications still in play. Their gaps matter most. */
export const ACTIVE_STATUSES: ApplicationStatus[] = ["applied", "interviewing"];

/** Finished either way (offer, rejected, withdrawn): their gaps no longer rank skills. */
export const FINISHED_STATUSES: ApplicationStatus[] = ["offer", "rejected", "withdrawn"];

export type JobGaps = { status: ApplicationStatus; gaps: Gap[] };

export type SkillToLearn = {
  skillId: number;
  name: string;
  jobs: number; // open jobs (active + saved) whose gaps include this skill
  activeJobs: number; // of those, how many you've applied to or are interviewing for
};

export function isOpen(status: ApplicationStatus): boolean {
  return !FINISHED_STATUSES.includes(status);
}

/**
 * Each skill counted once per open job it's a gap in ("needed by N jobs" means N
 * postings, not N requirement lines). Gaps not mapped to a skill are left out: there's
 * no skill to learn. Order: active jobs first, then open jobs, then name.
 */
export function rankSkillsToLearn(jobs: JobGaps[], limit: number): SkillToLearn[] {
  const bySkill = new Map<number, SkillToLearn>();
  for (const job of jobs) {
    if (!isOpen(job.status)) continue;
    const active = ACTIVE_STATUSES.includes(job.status);
    const seenInThisJob = new Set<number>();
    for (const gap of job.gaps) {
      const { skill_id: skillId, skill_name: name } = gap.requirement;
      if (skillId === null || name === null || seenInThisJob.has(skillId)) continue;
      seenInThisJob.add(skillId);
      const current = bySkill.get(skillId) ?? { skillId, name, jobs: 0, activeJobs: 0 };
      bySkill.set(skillId, {
        ...current,
        jobs: current.jobs + 1,
        activeJobs: current.activeJobs + (active ? 1 : 0),
      });
    }
  }
  return [...bySkill.values()]
    .sort((a, b) => b.activeJobs - a.activeJobs || b.jobs - a.jobs || a.name.localeCompare(b.name))
    .slice(0, limit);
}
