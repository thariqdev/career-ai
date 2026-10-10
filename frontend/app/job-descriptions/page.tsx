"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import GapList from "@/components/GapList";
import StatusBadge from "@/components/StatusBadge";
import JobMatchSummary from "@/components/JobMatchSummary";
import { shortDateTime } from "@/lib/interviews";
import {
  ACTIVE_STATUSES,
  APPLICATION_CLASSES,
  APPLICATION_LABEL,
  CLOSED_STATUSES,
} from "@/lib/applications";
import { Button, ButtonLink, Card, EmptyState, FieldError, Page, Pill, SectionHeading, inputClasses, invalidClasses } from "@/components/ui";
import type {
  ComparisonResult,
  ExtractionResponse,
  Gap,
  JobDescription,
  JobMatch,
} from "@/lib/types";

// Paste one job description and see its results here; "analyze another" resets the
// form. Every analyzed job is also listed below the form, and each has its own page
// (/job-descriptions/{id}) where it can be revisited and compared again.
type Stage = "creating" | "extracting" | "comparing" | "loading-gaps";

// Filters for the past-jobs list, by application status.
const FILTERS = {
  all: { label: "All", match: () => true },
  active: { label: "Active", match: (j: JobDescription) => ACTIVE_STATUSES.includes(j.application_status) },
  saved: { label: "Saved", match: (j: JobDescription) => j.application_status === "saved" },
  offer: { label: "Offer", match: (j: JobDescription) => j.application_status === "offer" },
  closed: { label: "Closed", match: (j: JobDescription) => CLOSED_STATUSES.includes(j.application_status) },
} as const;

type FilterKey = keyof typeof FILTERS;

// The user's job descriptions, newest first (GET /job-descriptions already orders
// them). Refetched whenever reloadKey changes, i.e. after each new analysis.
function PastJobs({ reloadKey }: { reloadKey: number }) {
  const [jobs, setJobs] = useState<JobDescription[] | null>(null);
  const [failed, setFailed] = useState(false);
  // When the list was loaded: "upcoming" is judged against this, not read during render.
  const [loadedAt, setLoadedAt] = useState(0);
  const [filter, setFilter] = useState<FilterKey>("all");

  useEffect(() => {
    let active = true;
    apiGet<JobDescription[]>("/job-descriptions")
      .then((list) => {
        if (!active) return;
        setJobs(list);
        setLoadedAt(Date.now());
      })
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [reloadKey]);

  return (
    <section className="mt-10">
      <SectionHeading title="Past job descriptions" hint="Newest first. Open one to revisit or compare again." />
      <div className="mt-3">
        {failed && <p className="text-sm text-not-verified">Could not load past job descriptions.</p>}
        {!failed && jobs === null && <p className="text-sm text-ink-soft">Loading…</p>}
        {jobs !== null && jobs.length === 0 && <EmptyState>None yet. Analyze one above.</EmptyState>}
        {jobs !== null && jobs.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {(Object.keys(FILTERS) as FilterKey[]).map((key) => (
              <Pill key={key} selected={filter === key} onClick={() => setFilter(key)}>
                {FILTERS[key].label} ({jobs.filter(FILTERS[key].match).length})
              </Pill>
            ))}
          </div>
        )}
        {jobs !== null && jobs.length > 0 && jobs.filter(FILTERS[filter].match).length === 0 && (
          <EmptyState>No jobs with this status.</EmptyState>
        )}
        {jobs !== null && jobs.length > 0 && (
          <ul className="flex flex-col gap-2">
            {jobs.filter(FILTERS[filter].match).map((job) => (
              <li key={job.id}>
                <Link
                  href={`/job-descriptions/${job.id}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm shadow-sm transition-colors hover:border-accent"
                >
                  <span>
                    <span className="font-medium text-ink">{job.title ?? "Untitled job"}</span>
                    <span className="text-ink-soft">
                      {job.company ? ` · ${job.company}` : ""} · {new Date(job.created_at).toLocaleDateString()}
                    </span>
                  </span>
                  <span className="flex items-center gap-3 text-ink-soft">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${APPLICATION_CLASSES[job.application_status]}`}>
                      {APPLICATION_LABEL[job.application_status]}
                      {job.applied_on ? ` · ${job.applied_on}` : ""}
                    </span>
                    {job.next_interview_at && new Date(job.next_interview_at).getTime() >= loadedAt && (
                      <span className="text-xs text-accent" title="Next interview">
                        📅 {shortDateTime(new Date(job.next_interview_at))}
                      </span>
                    )}
                    {job.requirements.length} requirement{job.requirements.length === 1 ? "" : "s"}
                    <span className="text-accent">Open →</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

const STAGE_LABEL: Record<Stage, string> = {
  creating: "Saving the posting",
  extracting: "Reading requirements",
  comparing: "Comparing with your proof",
  "loading-gaps": "Finding gaps",
};

const STAGES: Stage[] = ["creating", "extracting", "comparing", "loading-gaps"];

type PageState =
  | { status: "form" }
  | { status: "running"; stage: Stage }
  | {
      status: "done";
      jobDescription: JobDescription;
      extraction: ExtractionResponse;
      match: JobMatch;
      comparisons: ComparisonResult[];
      gaps: Gap[];
    }
  | { status: "error"; message: string };

export default function JobDescriptionsPage() {
  const [state, setState] = useState<PageState>({ status: "form" });
  const [rawText, setRawText] = useState("");
  const [textError, setTextError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [pastReloadKey, setPastReloadKey] = useState(0);

  function resetForm() {
    setRawText("");
    setTitle("");
    setCompany("");
    setSourceUrl("");
    setState({ status: "form" });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (rawText.trim() === "") {
      setTextError("Paste the job posting text first.");
      return;
    }
    try {
      setState({ status: "running", stage: "creating" });
      const jobDescription = await apiPost<JobDescription>("/job-descriptions", {
        raw_text: rawText,
        title: title.trim() === "" ? null : title,
        company: company.trim() === "" ? null : company,
        source_url: sourceUrl.trim() === "" ? null : sourceUrl,
      });

      setState({ status: "running", stage: "extracting" });
      const extraction = await apiPost<ExtractionResponse>(
        `/job-descriptions/${jobDescription.id}/extract`,
        {},
      );

      setState({ status: "running", stage: "comparing" });
      const comparisons = await apiPost<ComparisonResult[]>(
        `/job-descriptions/${jobDescription.id}/compare`,
        {},
      );

      setState({ status: "running", stage: "loading-gaps" });
      const [gaps, match] = await Promise.all([
        apiGet<Gap[]>(`/job-descriptions/${jobDescription.id}/gaps`),
        apiGet<JobMatch>(`/job-descriptions/${jobDescription.id}/match`),
      ]);

      setState({ status: "done", jobDescription, extraction, comparisons, gaps, match });
      setPastReloadKey((key) => key + 1);
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not reach the backend.",
      });
    }
  }

  return (
    <Page title="Job Descriptions">
      <p className="mt-1 text-sm text-ink-soft">
        Paste a job posting to see which requirements you can prove and where the gaps are.
      </p>

      {(state.status === "form" || state.status === "error") && (
        <Card className="mt-6">
          <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm text-ink-soft">
              Job posting text
              <textarea
                value={rawText}
                onChange={(e) => {
                  setRawText(e.target.value);
                  setTextError(null);
                }}
                rows={8}
                placeholder="Paste the full posting here…"
                aria-invalid={textError !== null}
                className={`${inputClasses} ${textError ? invalidClasses : ""}`}
              />
              <FieldError message={textError} />
            </label>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="flex flex-col gap-1 text-sm text-ink-soft">
                Title (optional)
                <input value={title} onChange={(e) => setTitle(e.target.value)} className={inputClasses} />
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink-soft">
                Company (optional)
                <input value={company} onChange={(e) => setCompany(e.target.value)} className={inputClasses} />
              </label>
              <label className="flex flex-col gap-1 text-sm text-ink-soft">
                Source URL (optional)
                <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} className={inputClasses} />
              </label>
            </div>
            <Button type="submit" variant="primary" className="self-start">
              Analyze
            </Button>
          </form>
          {state.status === "error" && (
            <p className="mt-3 text-sm text-not-verified">Error: {state.message}</p>
          )}
        </Card>
      )}

      {state.status === "running" && (
        <Card className="mt-6">
          <ol className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {STAGES.map((stage, index) => {
              const current = STAGES.indexOf(state.stage);
              return (
                <li
                  key={stage}
                  className={
                    index < current
                      ? "text-verified"
                      : index === current
                        ? "font-medium text-accent"
                        : "text-ink-soft"
                  }
                >
                  {index < current ? "✓ " : index === current ? "→ " : ""}
                  {STAGE_LABEL[stage]}
                </li>
              );
            })}
          </ol>
        </Card>
      )}

      {state.status === "done" && (
        <Card className="mt-6">
          <SectionHeading
            title={state.jobDescription.title ?? "Untitled job"}
            hint={state.jobDescription.company ?? undefined}
            actions={
              <ButtonLink href={`/job-descriptions/${state.jobDescription.id}`} variant="primary">
                Open this job&apos;s page →
              </ButtonLink>
            }
          />
          {state.extraction.note && <p className="mt-3 text-sm text-ink-soft">{state.extraction.note}</p>}
          <div className="mt-4">
            <JobMatchSummary
              match={state.match}
              onChanged={async () => {
                const id = state.jobDescription.id;
                const match = await apiGet<JobMatch>(`/job-descriptions/${id}/match`);
                setState((prev) => (prev.status === "done" ? { ...prev, match } : prev));
              }}
            />
          </div>
          {state.extraction.accepted.length === 0 ? (
            <div className="mt-4">
              <EmptyState>
                None of your saved skills appear in this posting. Requirements are found by
                matching the skills (and aliases) you&apos;ve added on the{" "}
                <Link href="/skills" className="underline">
                  Skills
                </Link>{" "}
                page — add the ones this job mentions, then analyze it again.
              </EmptyState>
            </div>
          ) : (
            <>
              <h3 className="mt-5 font-medium text-ink">Requirements</h3>
              <ul className="mt-2 flex flex-col gap-2">
                {state.extraction.accepted.map((requirement) => {
                  const comparison = state.comparisons.find(
                    (c) => c.job_requirement_id === requirement.id,
                  );
                  return (
                    <li
                      key={requirement.id}
                      className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2 text-sm text-ink"
                    >
                      <span>{requirement.requirement_text}</span>
                      <StatusBadge status={comparison?.knowledge_status ?? null} />
                    </li>
                  );
                })}
              </ul>

              <h3 className="mt-6 font-medium text-ink">Gaps</h3>
              <GapList gaps={state.gaps} />
            </>
          )}

          <div className="mt-6 border-t border-line pt-4">
            <Button onClick={resetForm}>Analyze another job description</Button>
          </div>
        </Card>
      )}

      <PastJobs reloadKey={pastReloadKey} />
    </Page>
  );
}
