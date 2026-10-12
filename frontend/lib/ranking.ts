/**
 * Which skills to learn first, from your job gaps and where each application stands.
 * Deterministic: no AI, and nothing here is guessed about you.
 *
 * Kept free of runtime imports (types only), so the plain Node test in
 * tests/ranking.test.mjs can load it directly.
 */

import type { ApplicationStatus, Gap, StudyLink } from "@/lib/types";

/** Applications still in play. Their gaps matter most. */
export const ACTIVE_STATUSES: ApplicationStatus[] = ["applied", "interviewing"];

/** Finished either way (offer, rejected, withdrawn): their gaps no longer rank skills. */
export const FINISHED_STATUSES: ApplicationStatus[] = ["offer", "rejected", "withdrawn"];

export type JobGaps = { status: ApplicationStatus; gaps: Gap[] };

export type SkillToLearn = {
  key: string; // the skill id, or "name:<name>" for a skill you haven't saved yet
  skillId: number | null; // null: named by the job but not one of your saved skills
  name: string;
  studyLinks: StudyLink[]; // YouTube searches, for a skill you haven't saved
  jobs: number; // open jobs (active + saved) whose gaps include this skill
  activeJobs: number; // of those, how many you've applied to or are interviewing for
};

export function isOpen(status: ApplicationStatus): boolean {
  return !FINISHED_STATUSES.includes(status);
}

/**
 * Each skill counted once per open job it's a gap in ("needed by N jobs" means N
 * postings, not N requirement lines). Skills you haven't saved count too (by name, since
 * stage 89: they're most of a job's skills). Requirement text that matches no skill is
 * left out: there's no skill to learn. Order: active jobs first, then open jobs, then name.
 */
export function rankSkillsToLearn(jobs: JobGaps[], limit: number): SkillToLearn[] {
  const bySkill = new Map<string, SkillToLearn>();
  for (const job of jobs) {
    if (!isOpen(job.status)) continue;
    const active = ACTIVE_STATUSES.includes(job.status);
    const seenInThisJob = new Set<string>();
    for (const gap of job.gaps) {
      const { skill_id: skillId, skill_name: name } = gap;
      if (name === null) continue;
      const key = skillId !== null ? String(skillId) : `name:${name.toLowerCase()}`;
      if (seenInThisJob.has(key)) continue;
      seenInThisJob.add(key);
      const current = bySkill.get(key) ?? { key, skillId, name, studyLinks: gap.study_links ?? [], jobs: 0, activeJobs: 0 };
      bySkill.set(key, {
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
