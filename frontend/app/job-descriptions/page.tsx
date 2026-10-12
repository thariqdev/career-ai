"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmDialog";
import GapList from "@/components/GapList";
import StatusBadge from "@/components/StatusBadge";
import JobMatchSummary from "@/components/JobMatchSummary";
import { shortDateTime } from "@/lib/interviews";
import { MATCH_CLASSES, MATCH_FILTERS, jobLabel, jobNumber, matchBand, sameText, type MatchBand } from "@/lib/jobs";
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
  JobDescriptionListItem,
  CVStatusResponse,
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

/** The match badge: "72% match", or why there's no number yet. */
function matchText(job: JobDescriptionListItem): { text: string; title: string } {
  if (job.match_percent !== null) {
    return { text: `${job.match_percent}% match`, title: `You have ${job.match_percent}% of the ${job.match_total} skills this job asks for.` };
  }
  if (job.match_total === 0) return { text: "Not compared", title: "No requirements found in this posting yet." };
  return { text: "Not compared", title: "Add your CV first: there's nothing to compare this job with yet." };
}

// The user's job descriptions, newest first (GET /job-descriptions already orders
// them). Refetched whenever reloadKey changes, i.e. after each new analysis.
function PastJobs({ reloadKey, onDeleted }: { reloadKey: number; onDeleted: (jobId: number) => void }) {
  const [jobs, setJobs] = useState<JobDescriptionListItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<{ id: number; message: string } | null>(null);
  const confirm = useConfirm();

  // Same rule and wording as "Delete job" on the job's own page.
  async function handleDelete(job: JobDescription) {
    const ok = await confirm({
      title: `Delete "${jobLabel(job, 40)}"?`,
      message:
        "Its requirements and comparison history go with it. Your skills, claims and evidence are not affected. This can't be undone.",
      confirmLabel: "Delete job",
      danger: true,
    });
    if (!ok) return;
    setDeleteError(null);
    setDeletingId(job.id);
    try {
      await apiDelete(`/job-descriptions/${job.id}`);
      setJobs((prev) => (prev === null ? prev : prev.filter((j) => j.id !== job.id)));
      onDeleted(job.id);
    } catch (err) {
      setDeleteError({ id: job.id, message: err instanceof ApiError ? err.message : "Could not delete the job." });
    } finally {
      setDeletingId(null);
    }
  }
  // When the list was loaded: "upcoming" is judged against this, not read during render.
  const [loadedAt, setLoadedAt] = useState(0);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [matchFilter, setMatchFilter] = useState<MatchBand | "any">("any");
  const byMatch = (key: MatchBand | "any") => (j: JobDescriptionListItem) =>
    key === "any" || matchBand(j.match_percent) === key;
  // Both filters apply together; each row of chips counts within the other's choice.
  const shown = jobs === null ? [] : jobs.filter(FILTERS[filter].match).filter(byMatch(matchFilter));

  useEffect(() => {
    let active = true;
    apiGet<JobDescriptionListItem[]>("/job-descriptions")
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
      <SectionHeading
        title="Pasted job descriptions"
        hint="Newest first, with how well you match each one. Open one to revisit or compare again."
      />
      <div className="mt-3">
        {failed && <p className="text-sm text-not-verified">Could not load your pasted job descriptions.</p>}
        {!failed && jobs === null && <p className="text-sm text-ink-soft">Loading…</p>}
        {jobs !== null && jobs.length === 0 && <EmptyState>None yet. Analyze one above.</EmptyState>}
        {jobs !== null && jobs.length > 0 && (
          <div className="mb-3 flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by application status">
              <span className="w-14 text-xs text-ink-soft">Status</span>
              {(Object.keys(FILTERS) as FilterKey[]).map((key) => (
                <Pill key={key} selected={filter === key} onClick={() => setFilter(key)}>
                  {FILTERS[key].label} ({jobs.filter(byMatch(matchFilter)).filter(FILTERS[key].match).length})
                </Pill>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by match">
              <span className="w-14 text-xs text-ink-soft">Match</span>
              {MATCH_FILTERS.map(({ key, label }) => (
                <Pill key={key} selected={matchFilter === key} onClick={() => setMatchFilter(key)}>
                  {label} ({jobs.filter(FILTERS[filter].match).filter(byMatch(key)).length})
                </Pill>
              ))}
            </div>
          </div>
        )}
        {jobs !== null && jobs.length > 0 && shown.length === 0 && (
          <EmptyState>No jobs match these filters.</EmptyState>
        )}
        {jobs !== null && jobs.length > 0 && (
          <ul className="flex flex-col gap-2">
            {shown.map((job) => (
              <li
                key={job.id}
                className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface pr-3 text-sm shadow-sm transition-colors hover:border-accent"
              >
                {/* The row opens the job; Delete sits beside the link (a button can't be inside one). */}
                <Link
                  href={`/job-descriptions/${job.id}`}
                  className="flex min-w-0 flex-1 flex-wrap items-center justify-between gap-2 px-4 py-3"
                >
                  <span>
                    <span className="mr-1.5 text-xs text-ink-soft" title="The number the assistant uses for this job">{jobNumber(job)}</span>
                    <span className="font-medium text-ink">{jobLabel(job)}</span>
                    <span className="text-ink-soft">
                      {job.company ? ` · ${job.company}` : ""} · {new Date(job.created_at).toLocaleDateString()}
                    </span>
                  </span>
                  <span className="flex items-center gap-3 text-ink-soft">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${MATCH_CLASSES[matchBand(job.match_percent)]}`}
                      title={matchText(job).title}
                    >
                      {matchText(job).text}
                    </span>
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${APPLICATION_CLASSES[job.application_status]}`}>
                      {APPLICATION_LABEL[job.application_status]}
                      {job.applied_on ? ` · ${job.applied_on}` : ""}
                    </span>
                    {job.next_interview_at && new Date(job.next_interview_at).getTime() >= loadedAt && (
                      <span className="text-xs text-accent" title="Next interview">
                        📅 {shortDateTime(new Date(job.next_interview_at))}
                      </span>
                    )}
                    {/* The match's count (what the job's page says it asks for), not the saved
                        requirement rows, which miss skills named in the posting itself. */}
                    {job.match_total} skill{job.match_total === 1 ? "" : "s"}
                    <span className="text-accent">Open →</span>
                  </span>
                </Link>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={deletingId !== null}
                  onClick={() => handleDelete(job)}
                  aria-label={`Delete ${jobLabel(job, 40)}`}
                >
                  {deletingId === job.id ? "Deleting…" : "Delete"}
                </Button>
                {deleteError?.id === job.id && (
                  <p className="w-full px-4 pb-2 text-xs text-not-verified">{deleteError.message}</p>
                )}
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
  const [duplicateOf, setDuplicateOf] = useState<JobDescription | null>(null);
  // null while loading; false: no skill on the CV and no claim yet (add the CV first).
  const [hasCv, setHasCv] = useState<boolean | null>(null);

  // Fetch first, then set state only in the promise callbacks.
  useEffect(() => {
    let active = true;
    apiGet<CVStatusResponse[]>("/cv/status")
      .then(
        (statuses) =>
          active &&
          setHasCv(statuses.some((s) => s.cv_status === "present" || s.knowledge_status !== null)),
      )
      .catch(() => active && setHasCv(null)); // unknown: show no hint rather than a wrong one
    return () => {
      active = false;
    };
  }, []);
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
    // Same posting already added? Say so under the box, with a link, and save nothing.
    // (The backend refuses it too, with 409, in case this check is skipped.)
    try {
      const existing = (await apiGet<JobDescription[]>("/job-descriptions")).find((j) =>
        sameText(j.raw_text, rawText),
      );
      if (existing) {
        setDuplicateOf(existing);
        setTextError(
          `You already added this exact job description on ${new Date(existing.created_at).toLocaleDateString()}.`,
        );
        return;
      }
    } catch {
      // The list couldn't be loaded: carry on; the backend still refuses a duplicate.
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
      // A duplicate refused by the backend (409) belongs under the paste box, like the
      // check above; anything else is shown as a page error.
      if (error instanceof ApiError && error.status === 409) {
        setTextError(error.message);
        setState({ status: "form" });
        return;
      }
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

      {hasCv === false && (state.status === "form" || state.status === "error") && (
        <Card className="mt-6 border-warm/50 bg-warm-soft/40">
          <SectionHeading
            title="Step 1: add your CV first"
            hint="Career AI compares each job with the skills on your CV. Add your CV first, then paste jobs here to see your match and what's missing. You can still paste a job now; its match will show once your CV is in."
            actions={
              <ButtonLink href="/cv" variant="primary">
                Add my CV →
              </ButtonLink>
            }
          />
        </Card>
      )}

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
                  setDuplicateOf(null);
                }}
                rows={8}
                placeholder="Paste the full posting here…"
                aria-invalid={textError !== null}
                className={`${inputClasses} ${textError ? invalidClasses : ""}`}
              />
              <FieldError message={textError} />
              {duplicateOf && (
                <Link href={`/job-descriptions/${duplicateOf.id}`} className="text-xs font-medium text-accent underline">
                  Open it →
                </Link>
              )}
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
            title={jobLabel(state.jobDescription)}
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
          {!state.match.has_cv ? null : state.extraction.accepted.length === 0 ? (
            <div className="mt-4">
              <EmptyState>
                None of your saved skills appear in this posting. Requirements are found by
                matching the skills (and aliases) you&apos;ve added on the{" "}
                <Link href="/skills" className="underline">
                  Skills
                </Link>{" "}
                page. Your match above already shows what this job asks for.
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

      <PastJobs
        reloadKey={pastReloadKey}
        onDeleted={(jobId) => {
          // The result card above shouldn't keep showing a job that no longer exists.
          if (state.status === "done" && state.jobDescription.id === jobId) resetForm();
          setDuplicateOf((prev) => (prev?.id === jobId ? null : prev));
        }}
      />
    </Page>
  );
}
