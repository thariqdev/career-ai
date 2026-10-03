"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "@/lib/api";
import GapList from "@/components/GapList";
import LearnLinks from "@/components/LearnLinks";
import { ButtonLink, Card, EmptyState, Page, SectionHeading } from "@/components/ui";
import { APPLICATION_CLASSES, APPLICATION_LABEL, APPLICATION_STATUSES } from "@/lib/applications";
import { isOpen, rankSkillsToLearn, type SkillToLearn } from "@/lib/ranking";
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

  // Ranked by where each application stands: active jobs first, finished ones ignored
  // (lib/ranking.ts). One request for every listed skill's learning path.
  const skillsToLearn = rankSkillsToLearn(
    jobDescriptions.map((jd, i) => ({ status: jd.application_status, gaps: gapsPerJob[i] })),
    MAX_SKILLS_TO_LEARN,
  );
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
    // Only jobs still open (not offer/rejected/withdrawn) count as gaps to close.
    totalGaps: gapsPerJob.reduce(
      (sum, gaps, i) => sum + (isOpen(jobDescriptions[i].application_status) ? gaps.length : 0),
      0,
    ),
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
                  {item.activeJobs > 0 && ` · ${item.activeJobs} you've applied to`}
                </p>
                {item.activeJobs > 0 && (
                  <span className="mt-1 inline-block rounded bg-warm-soft px-2 py-0.5 text-xs font-medium text-warm">
                    for an application
                  </span>
                )}
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
        <StatTile value={state.totalGaps} label="Open gaps (open jobs)" href="/job-descriptions" />
        <StatTile
          value={state.jobDescriptions.length}
          label="Job descriptions analyzed"
          href="/job-descriptions"
        />
      </div>

      {state.jobDescriptions.some((j) => j.application_status !== "saved") && (
        <section className="mt-6">
          <Link
            href="/job-descriptions"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm shadow-sm transition-colors hover:border-accent"
          >
            <span className="font-medium text-ink">Your applications:</span>
            {APPLICATION_STATUSES.filter((s) => s !== "saved").map((status) => {
              const n = state.jobDescriptions.filter((j) => j.application_status === status).length;
              return n === 0 ? null : (
                <span key={status} className={`rounded px-2 py-0.5 text-xs font-medium ${APPLICATION_CLASSES[status]}`}>
                  {n} {APPLICATION_LABEL[status].toLowerCase()}
                </span>
              );
            })}
          </Link>
        </section>
      )}

      <section className="mt-10">
        <SectionHeading
          title="Skills to learn"
          hint="Skills your live applications need come first, then the ones most open jobs ask for. Closed jobs aren't counted."
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
