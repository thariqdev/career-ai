"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiGet, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { Button, EmptyState, Page } from "@/components/ui";
import { MODE_LABEL } from "@/lib/learning";
import { isWebLink } from "@/lib/links";
import type { InterviewPrep, InterviewPrepItem } from "@/lib/types";

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; prep: InterviewPrep };

// Statuses with real evidence behind them: no study links needed on their cards.
const PROVEN = new Set(["verified", "partial"]);

function PrepCard({ item }: { item: InterviewPrepItem }) {
  return (
    <li className="break-inside-avoid rounded-lg border border-line bg-surface p-5 shadow-sm print:shadow-none">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-ink">{item.requirement_text}</span>
        <span className="rounded bg-ground px-1.5 py-0.5 text-xs text-ink-soft">
          {item.is_required ? "required" : "nice to have"}
        </span>
        {item.status === "unmapped" ? (
          <span className="text-xs text-ink-soft">not in your skill list</span>
        ) : (
          <StatusBadge status={item.status === "no_claim" ? null : item.status} />
        )}
      </div>

      <p className="mt-2 text-sm text-ink">{item.guidance}</p>
      {item.cv_warning && <p className="mt-1 text-sm text-warm">{item.cv_warning}</p>}

      {item.evidence.length > 0 && (
        <div className="mt-2 text-sm">
          {/* Only proven skills get "Talk about"; evidence linked to an unproven claim is
              listed neutrally, so the card doesn't say "not proven" and "talk about it". */}
          <p className="text-ink-soft">
            {PROVEN.has(item.status) ? "Talk about:" : "Evidence you've linked:"}
          </p>
          <ul className="ml-4 list-disc text-ink">
            {item.evidence.map((e) => (
              <li key={e.id}>
                {e.url && isWebLink(e.url) ? (
                  <a href={e.url} target="_blank" rel="noopener noreferrer" className="underline">
                    {e.title}
                  </a>
                ) : (
                  e.title
                )}
                {e.source && <span className="text-ink-soft"> ({e.source})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!PROVEN.has(item.status) && item.study_links.length > 0 && (
        <p className="mt-2 text-sm text-ink-soft print:hidden">
          Study:{" "}
          {item.study_links.map((link, i) => (
            <span key={link.mode}>
              {i > 0 && " · "}
              <a href={link.url} target="_blank" rel="noopener noreferrer" className="text-accent underline">
                {MODE_LABEL[link.mode]}
              </a>
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

export default function InterviewPrepPage() {
  const params = useParams<{ id: string }>();
  const jobId = Number(params.id);
  const [state, setState] = useState<PageState>({ status: "loading" });

  // Fetch first, then set state only in the promise callbacks.
  useEffect(() => {
    let active = true;
    apiGet<InterviewPrep>(`/job-descriptions/${jobId}/interview-prep`)
      .then((prep) => active && setState({ status: "loaded", prep }))
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
  }, [jobId]);

  if (state.status === "loading") {
    return (
      <Page>
        <p className="text-ink-soft">Loading…</p>
      </Page>
    );
  }
  if (state.status === "error") {
    return (
      <Page>
        <p className="text-not-verified">Error: {state.message}</p>
      </Page>
    );
  }

  const { prep } = state;
  return (
    <Page>
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href={`/job-descriptions/${jobId}`} className="text-sm text-ink-soft hover:text-ink">
          ← Back to the job
        </Link>
        <Button onClick={() => window.print()}>Print</Button>
      </div>

      <h1 className="mt-3 font-display text-3xl text-ink">
        Interview prep: {prep.title ?? "Untitled job"}
        {prep.company ? ` at ${prep.company}` : ""}
      </h1>
      <p className="mt-1 text-sm text-ink-soft">
        Every line here comes from your own saved claims and evidence, using your proof as it
        is right now. Nothing is made up: where you haven&apos;t proven a skill, it tells you
        not to claim it.
      </p>

      {prep.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState>
            This job has no requirements yet, so there&apos;s nothing to prepare. Use &ldquo;Look
            for new skills&rdquo; on the job&apos;s page first.
          </EmptyState>
        </div>
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {prep.items.map((item) => (
            <PrepCard key={item.key} item={item} />
          ))}
        </ul>
      )}
    </Page>
  );
}
