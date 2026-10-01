"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import GapList from "@/components/GapList";
import StatusBadge from "@/components/StatusBadge";
import type {
  ComparisonResult,
  ExtractionResponse,
  Gap,
  JobDescription,
} from "@/lib/types";

// There is no GET-all-job-descriptions endpoint on the backend yet, so this page
// is single-shot: paste one job description, see its results, then "analyze
// another" throws the results away and shows a fresh form. A real list/history
// page is a gap for later, not something to add here.
type Stage = "creating" | "extracting" | "comparing" | "loading-gaps";

const STAGE_LABEL: Record<Stage, string> = {
  creating: "Creating…",
  extracting: "Extracting…",
  comparing: "Comparing…",
  "loading-gaps": "Loading gaps…",
};

type PageState =
  | { status: "form" }
  | { status: "running"; stage: Stage }
  | {
      status: "done";
      jobDescription: JobDescription;
      extraction: ExtractionResponse;
      comparisons: ComparisonResult[];
      gaps: Gap[];
    }
  | { status: "error"; message: string };

export default function JobDescriptionsPage() {
  const [state, setState] = useState<PageState>({ status: "form" });
  const [rawText, setRawText] = useState("");
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");

  function resetForm() {
    setRawText("");
    setTitle("");
    setCompany("");
    setSourceUrl("");
    setState({ status: "form" });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
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
      const gaps = await apiGet<Gap[]>(`/job-descriptions/${jobDescription.id}/gaps`);

      setState({ status: "done", jobDescription, extraction, comparisons, gaps });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not reach the backend.",
      });
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-ink">Job Descriptions</h1>

      {(state.status === "form" || state.status === "error") && (
        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col text-sm text-ink-soft">
            Job posting text
            <textarea
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              required
              rows={8}
              className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
            />
          </label>
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col text-sm text-ink-soft">
              Title (optional)
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
              />
            </label>
            <label className="flex flex-col text-sm text-ink-soft">
              Company (optional)
              <input
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
              />
            </label>
            <label className="flex flex-col text-sm text-ink-soft">
              Source URL (optional)
              <input
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
              />
            </label>
          </div>
          <button
            type="submit"
            className="self-start rounded bg-accent px-4 py-1.5 text-sm text-surface"
          >
            Analyze
          </button>
        </form>
      )}

      {state.status === "error" && (
        <p className="mt-2 text-sm text-not-verified">Error: {state.message}</p>
      )}

      {state.status === "running" && (
        <p className="mt-6 text-ink-soft">{STAGE_LABEL[state.stage]}</p>
      )}

      {state.status === "done" && (
        <div className="mt-8">
          {state.extraction.accepted.length === 0 ? (
            <p className="text-ink-soft">
              None of your saved skills appear in this posting. Requirements are found by
              matching the skills (and aliases) you&apos;ve added on the{" "}
              <Link href="/skills" className="underline">
                Skills
              </Link>{" "}
              page — add the ones this job mentions, then analyze it again.
            </p>
          ) : (
            <>
              <h2 className="font-display text-lg text-ink">Requirements</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {state.extraction.accepted.map((requirement) => {
                  const comparison = state.comparisons.find(
                    (c) => c.job_requirement_id === requirement.id,
                  );
                  return (
                    <li key={requirement.id} className="flex items-center gap-3 text-sm text-ink">
                      <span>{requirement.requirement_text}</span>
                      <StatusBadge status={comparison?.knowledge_status ?? null} />
                    </li>
                  );
                })}
              </ul>

              <h2 className="mt-6 font-display text-lg text-ink">Gaps</h2>
              <GapList gaps={state.gaps} />
            </>
          )}

          <button
            type="button"
            onClick={resetForm}
            className="mt-6 rounded border border-line px-4 py-1.5 text-sm text-ink"
          >
            Analyze another job description
          </button>
        </div>
      )}
    </main>
  );
}
