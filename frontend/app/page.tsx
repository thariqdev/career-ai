"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "@/lib/api";
import GapList from "@/components/GapList";
import LearnLinks from "@/components/LearnLinks";
import { ButtonLink, Card, EmptyState, Page, SectionHeading } from "@/components/ui";
import { PROGRESS_LABEL, useLearningResources } from "@/lib/learning";
import type {
  CVStatusResponse,
  Gap,
  JobDescription,
  LearningPath,
  LearningProgress,
  LearningProgressStatus,
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
  nextStepBySkill: Record<number, string | null>;
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

async function fetchDashboard(): Promise<Loaded> {
  // Independent requests, in parallel. GET /job-descriptions is already newest-first,
  // and GET /cv/status is ordered by skill name.
  const [userSkills, jobDescriptions, allProgress, cvStatuses] = await Promise.all([
    apiGet<UserSkill[]>("/user-skills"),
    apiGet<JobDescription[]>("/job-descriptions"),
    apiGet<LearningProgress[]>("/learning-progress"),
    apiGet<CVStatusResponse[]>("/cv/status"),
  ]);

  // One gaps request per job description (there's no all-jobs gaps endpoint). Read-only:
  // this triggers no new comparisons, it reads whatever was last computed for each job.
  const gapsPerJob = await Promise.all(
    jobDescriptions.map((jd) => apiGet<Gap[]>(`/job-descriptions/${jd.id}/gaps`)),
  );

  const progressBySkill: Record<number, LearningProgressStatus> = {};
  for (const p of allProgress) progressBySkill[p.skill_id] = p.status;

  // One request for every listed skill's learning path (not one per skill).
  const skillsToLearn = rankSkillsToLearn(gapsPerJob);
  const paths =
    skillsToLearn.length === 0
      ? []
      : await apiGet<LearningPath[]>(
          `/learning-paths?${skillsToLearn.map((s) => `skill_ids=${s.skillId}`).join("&")}`,
        );
  const nextStepBySkill: Record<number, string | null> = {};
  for (const path of paths) nextStepBySkill[path.skill_id] = path.next_step;

  return {
    status: "loaded",
    verifiedCount: userSkills.filter((us) => us.status === "verified").length,
    totalGaps: gapsPerJob.reduce((sum, gaps) => sum + gaps.length, 0),
    jobDescriptions,
    mostRecentGaps: gapsPerJob[0] ?? [],
    skillsToLearn,
    progressBySkill,
    nextStepBySkill,
    // Skills missing from /cv/status have no recommendation anyway (no claim, no CV mark).
    recommendations: cvStatuses
      .map((c) => c.recommendation)
      .filter((r): r is string => r !== null)
      .slice(0, MAX_RECOMMENDATIONS),
  };
}

function SkillsToLearn({
  items,
  progressBySkill,
  nextStepBySkill,
}: {
  items: SkillToLearn[];
  progressBySkill: Record<number, LearningProgressStatus>;
  nextStepBySkill: Record<number, string | null>;
}) {
  const learning = useLearningResources(items.map((item) => item.skillId));

  if (items.length === 0) {
    return (
      <div className="mt-3">
        <EmptyState>
          No open gaps right now. Paste a job posting on{" "}
          <Link href="/job-descriptions" className="underline">
            Job Descriptions
          </Link>{" "}
          to see what to learn next.
        </EmptyState>
      </div>
    );
  }
  return (
    <ul className="mt-3 grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <li key={item.skillId}>
          <Card className="flex h-full flex-col gap-3 p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <Link href={`/skills/${item.skillId}`} className="font-medium text-ink hover:underline">
                  {item.name}
                </Link>
                <p className="text-xs text-ink-soft">
                  needed by {item.jobs} {item.jobs === 1 ? "job" : "jobs"}
                </p>
              </div>
              {progressBySkill[item.skillId] && (
                <span className="rounded bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent">
                  {PROGRESS_LABEL[progressBySkill[item.skillId]].toLowerCase()}
                </span>
              )}
            </div>
            {item.skillId in nextStepBySkill && (
              <ButtonLink
                href={`/skills/${item.skillId}`}
                variant={nextStepBySkill[item.skillId] ? "primary" : "plain"}
                className="self-start"
              >
                {nextStepBySkill[item.skillId]
                  ? `Next step: ${nextStepBySkill[item.skillId]} →`
                  : "Learning path complete ✓"}
              </ButtonLink>
            )}
            {learning[item.skillId] && (
              <div className="mt-auto border-t border-line pt-3">
                <LearnLinks learning={learning[item.skillId]} />
              </div>
            )}
          </Card>
        </li>
      ))}
    </ul>
  );
}

function StatTile({ value, label, href }: { value: number; label: string; href: string }) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-line bg-surface px-4 py-3 shadow-sm transition-colors hover:border-accent"
    >
      <p className="font-display text-3xl text-ink">{value}</p>
      <p className="text-sm text-ink-soft">{label}</p>
    </Link>
  );
}

type State = { status: "loading" } | { status: "error"; message: string } | Loaded;

export default function DashboardPage() {
  const [state, setState] = useState<State>({ status: "loading" });

  // Fetch first, then set state only in the promise callbacks: no synchronous
  // setState inside the effect (react-hooks/set-state-in-effect).
  useEffect(() => {
    let active = true;
    fetchDashboard()
      .then((loaded) => active && setState(loaded))
      .catch(
        (error) =>
          active &&
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "Could not reach the backend.",
          }),
      );
    return () => {
      active = false;
    };
  }, []);

  if (state.status === "loading") {
    return (
      <Page title="Dashboard">
        <p className="mt-4 text-ink-soft">Loading…</p>
      </Page>
    );
  }

  if (state.status === "error") {
    return (
      <Page title="Dashboard">
        <p className="mt-4 text-not-verified">Error: {state.message}</p>
      </Page>
    );
  }

  const mostRecent = state.jobDescriptions[0] ?? null;

  return (
    <Page title="Dashboard">
      <p className="mt-1 text-sm text-ink-soft">
        What you can prove, what jobs ask for, and what to learn next.
      </p>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile value={state.verifiedCount} label="Verified skills" href="/skills" />
        <StatTile value={state.totalGaps} label="Open gaps" href="/job-descriptions" />
        <StatTile
          value={state.jobDescriptions.length}
          label="Job descriptions analyzed"
          href="/job-descriptions"
        />
      </div>

      <section className="mt-10">
        <SectionHeading
          title="Skills to learn"
          hint="Ranked by how many of your saved jobs ask for them."
        />
        <SkillsToLearn
          items={state.skillsToLearn}
          progressBySkill={state.progressBySkill}
          nextStepBySkill={state.nextStepBySkill}
        />
      </section>

      <section className="mt-10">
        <SectionHeading
          title="Recent comparison"
          actions={
            mostRecent && (
              <ButtonLink href={`/job-descriptions/${mostRecent.id}`}>Open job →</ButtonLink>
            )
          }
        />
        <div className="mt-3">
          {mostRecent === null ? (
            <EmptyState>
              No job descriptions yet. Paste one on the{" "}
              <Link href="/job-descriptions" className="underline">
                Job Descriptions
              </Link>{" "}
              page to see a comparison here.
            </EmptyState>
          ) : (
            <Card>
              <p className="font-medium text-ink">
                {mostRecent.title ?? "Untitled"}
                {mostRecent.company && (
                  <span className="font-normal text-ink-soft"> · {mostRecent.company}</span>
                )}
              </p>
              <GapList gaps={state.mostRecentGaps} />
            </Card>
          )}
        </div>
      </section>

      <section className="mt-10">
        <SectionHeading title="CV recommendations" />
        <div className="mt-3">
          {state.recommendations.length === 0 ? (
            <EmptyState>No CV recommendations right now.</EmptyState>
          ) : (
            <Card>
              <ul className="flex flex-col gap-2 text-sm text-ink">
                {state.recommendations.map((recommendation, index) => (
                  <li key={index} className="flex gap-2">
                    <span className="text-warm" aria-hidden>
                      •
                    </span>
                    {recommendation}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </section>
    </Page>
  );
}
