"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "@/lib/api";
import GapList from "@/components/GapList";
import LearnLinks from "@/components/LearnLinks";
import { PROGRESS_LABEL, useLearningResources } from "@/lib/learning";
import type {
  CVStatusResponse,
  Gap,
  JobDescription,
  LearningProgress,
  LearningProgressStatus,
  Skill,
  UserSkill,
} from "@/lib/types";

// The maximum number of CV recommendations shown at once, so a large skill
// list doesn't turn this section into a second full page of its own.
const MAX_RECOMMENDATIONS = 5;
const MAX_SKILLS_TO_LEARN = 8;

type SkillToLearn = { skillId: number; name: string; jobs: number };

type Loaded = {
  status: "loaded";
  verifiedCount: number;
  totalGaps: number;
  jobDescriptions: JobDescription[];
  mostRecentGaps: Gap[];
  skillsToLearn: SkillToLearn[];
  progressBySkill: Record<number, LearningProgressStatus>;
  recommendations: string[];
};

// Each skill counted once per job description it's a gap in, so "needed by N
// jobs" means N different postings, not N requirement lines. Gaps not mapped to
// a skill are left out: there's no skill to learn or search for.
function rankSkillsToLearn(gapsPerJob: Gap[][]): SkillToLearn[] {
  const bySkill = new Map<number, SkillToLearn>();
  for (const gaps of gapsPerJob) {
    const seenInThisJob = new Set<number>();
    for (const gap of gaps) {
      const { skill_id: skillId, skill_name: name } = gap.requirement;
      if (skillId === null || name === null || seenInThisJob.has(skillId)) continue;
      seenInThisJob.add(skillId);
      const jobs = (bySkill.get(skillId)?.jobs ?? 0) + 1;
      bySkill.set(skillId, { skillId, name, jobs });
    }
  }
  return [...bySkill.values()]
    .sort((a, b) => b.jobs - a.jobs || a.name.localeCompare(b.name))
    .slice(0, MAX_SKILLS_TO_LEARN);
}

function SkillsToLearn({
  items,
  progressBySkill,
}: {
  items: SkillToLearn[];
  progressBySkill: Record<number, LearningProgressStatus>;
}) {
  const learning = useLearningResources(items.map((item) => item.skillId));

  if (items.length === 0) {
    return <p className="mt-2 text-ink-soft">No open gaps right now.</p>;
  }
  return (
    <ul className="mt-3 flex flex-col gap-3">
      {items.map((item) => (
        <li key={item.skillId} className="flex flex-col gap-1 text-sm text-ink">
          <span>
            {item.name}{" "}
            <span className="text-ink-soft">
              — needed by {item.jobs} {item.jobs === 1 ? "job" : "jobs"}
            </span>
            {progressBySkill[item.skillId] && (
              <span className="ml-2 rounded bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
                {PROGRESS_LABEL[progressBySkill[item.skillId]].toLowerCase()}
              </span>
            )}
          </span>
          {learning[item.skillId] && <LearnLinks learning={learning[item.skillId]} />}
        </li>
      ))}
    </ul>
  );
}

type State = { status: "loading" } | { status: "error"; message: string } | Loaded;

export default function DashboardPage() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    async function load() {
      setState({ status: "loading" });
      try {
        const userSkills = await apiGet<UserSkill[]>("/user-skills");
        const verifiedCount = userSkills.filter((us) => us.status === "verified").length;

        // GET /job-descriptions already returns most-recent-first.
        const jobDescriptions = await apiGet<JobDescription[]>("/job-descriptions");

        // One gaps request per job description — the same accepted N+1 pattern
        // already used on the Skills and Skill Detail pages, just applied to a
        // different list. Read-only: this triggers no new comparisons, it only
        // reads whatever was last computed for each job description.
        const gapsPerJob = await Promise.all(
          jobDescriptions.map((jd) => apiGet<Gap[]>(`/job-descriptions/${jd.id}/gaps`)),
        );
        const totalGaps = gapsPerJob.reduce((sum, gaps) => sum + gaps.length, 0);
        const mostRecentGaps = gapsPerJob[0] ?? [];
        const skillsToLearn = rankSkillsToLearn(gapsPerJob);

        const allProgress = await apiGet<LearningProgress[]>("/learning-progress");
        const progressBySkill: Record<number, LearningProgressStatus> = {};
        for (const p of allProgress) progressBySkill[p.skill_id] = p.status;

        const skills = await apiGet<Skill[]>("/skills");
        const cvStatuses = await Promise.all(
          skills.map((s) => apiGet<CVStatusResponse>(`/skills/${s.id}/cv-status`)),
        );
        const recommendations = cvStatuses
          .map((c) => c.recommendation)
          .filter((r): r is string => r !== null)
          .slice(0, MAX_RECOMMENDATIONS);

        setState({
          status: "loaded",
          verifiedCount,
          totalGaps,
          jobDescriptions,
          mostRecentGaps,
          skillsToLearn,
          progressBySkill,
          recommendations,
        });
      } catch (error) {
        setState({
          status: "error",
          message: error instanceof ApiError ? error.message : "Could not reach the backend.",
        });
      }
    }
    load();
  }, []);

  if (state.status === "loading") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-not-verified">Error: {state.message}</p>
      </main>
    );
  }

  const mostRecent = state.jobDescriptions[0] ?? null;

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-ink">Dashboard</h1>

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div className="rounded border border-line px-4 py-3">
          <p className="text-2xl text-ink">{state.verifiedCount}</p>
          <p className="text-sm text-ink-soft">Verified skills</p>
        </div>
        <div className="rounded border border-line px-4 py-3">
          <p className="text-2xl text-ink">{state.totalGaps}</p>
          <p className="text-sm text-ink-soft">Open gaps</p>
        </div>
        <div className="rounded border border-line px-4 py-3">
          <p className="text-2xl text-ink">{state.jobDescriptions.length}</p>
          <p className="text-sm text-ink-soft">Job descriptions analyzed</p>
        </div>
      </div>

      <section className="mt-8">
        <h2 className="font-display text-lg text-ink">Skills to learn</h2>
        <SkillsToLearn items={state.skillsToLearn} progressBySkill={state.progressBySkill} />
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg text-ink">Recent comparison</h2>
        {mostRecent === null ? (
          <p className="mt-2 text-ink-soft">
            No job descriptions yet. Paste one on the{" "}
            <Link href="/job-descriptions" className="underline">
              Job Descriptions
            </Link>{" "}
            page to see a comparison here.
          </p>
        ) : (
          <div className="mt-2">
            <p className="text-ink">
              {mostRecent.title ?? "Untitled"}
              {mostRecent.company ? ` — ${mostRecent.company}` : ""}
            </p>
            <GapList gaps={state.mostRecentGaps} />
          </div>
        )}
      </section>

      <section className="mt-8">
        <h2 className="font-display text-lg text-ink">CV recommendations</h2>
        {state.recommendations.length === 0 ? (
          <p className="mt-2 text-ink-soft">No CV recommendations right now.</p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2 text-sm text-ink">
            {state.recommendations.map((recommendation, index) => (
              <li key={index}>{recommendation}</li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
