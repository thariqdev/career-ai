"use client";

import { useState } from "react";
import Link from "next/link";
import { apiPost, ApiError } from "@/lib/api";
import LearnLinks from "@/components/LearnLinks";
import { ButtonLink, Card, SectionHeading } from "@/components/ui";
import { useLearningResources } from "@/lib/learning";
import type { JobMatch, MatchItem } from "@/lib/types";

// Same searches the backend builds for saved skills (learning_service.SEARCH_QUERY_TEMPLATES),
// for a missing skill that isn't saved yet and so has no learning page.
function youtubeSearch(query: string): string {
  return `https://www.youtube.com/results?${new URLSearchParams({ search_query: query })}`;
}

function Chip({ item, tone }: { item: MatchItem; tone: "proven" | "cv" }) {
  const classes = tone === "proven" ? "bg-verified-bg text-verified" : "bg-accent-soft text-accent";
  const label = (
    <span className={`rounded-full px-3 py-0.5 text-sm ${classes}`}>
      {tone === "proven" ? "✓ " : ""}
      {item.name}
    </span>
  );
  return item.skill_id === null ? label : <Link href={`/skills/${item.skill_id}`}>{label}</Link>;
}

/**
 * How much of this job you have, from the backend's match_service (always current):
 * proven (evidence-backed), on your CV (you say you have it), missing. Missing skills
 * come first, each with ways to learn it; one that isn't saved yet can be added in a
 * click (just its name: no claim). onChanged lets the page reload after an add.
 */
export default function JobMatchSummary({
  match,
  onChanged,
}: {
  match: JobMatch;
  onChanged: () => Promise<void> | void;
}) {
  const learning = useLearningResources(
    match.missing.flatMap((m) => (m.skill_id === null ? [] : [m.skill_id])),
  );
  const [adding, setAdding] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function addSkill(name: string) {
    setError(null);
    setAdding(name);
    try {
      await apiPost("/skills", { name, category: null });
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the skill.");
    } finally {
      setAdding(null);
    }
  }

  if (match.total === 0) {
    return (
      <Card>
        <SectionHeading
          title="Your match"
          hint="No skills found in this posting yet. Add the skills it asks for on the Skills page."
        />
      </Card>
    );
  }

  const have = match.proven.length + match.on_cv.length;
  return (
    <Card>
      {match.has_cv ? (
        <SectionHeading
          title="Your match"
          hint={`You have ${have} of the ${match.total} skills this job asks for.`}
        />
      ) : (
        // Nothing to compare with yet: a 0% here would only be discouraging and wrong.
        <SectionHeading
          title="Add your CV to see your match"
          hint={`Career AI compares each job with the skills on your CV. You haven't added your CV yet, so there's nothing to compare. This job asks for ${match.total} skill${match.total === 1 ? "" : "s"}, listed below.`}
          actions={
            <ButtonLink href="/cv" variant="primary">
              Add my CV →
            </ButtonLink>
          }
        />
      )}
      {match.has_cv && (
      <div className="mt-3 flex items-center gap-4">
        <span className="font-display text-4xl text-ink">{match.percent}%</span>
        <div className="flex-1">
          <div className="flex h-3 overflow-hidden rounded-full bg-not-verified-bg" aria-hidden>
            <div className="bg-verified" style={{ width: `${(100 * match.proven.length) / match.total}%` }} />
            <div className="bg-accent" style={{ width: `${(100 * match.on_cv.length) / match.total}%` }} />
          </div>
          <p className="mt-1 text-xs text-ink-soft">
            <span className="text-verified">■</span> {match.proven.length} proven ·{" "}
            <span className="text-accent">■</span> {match.on_cv.length} on your CV, not proven yet ·{" "}
            <span className="text-not-verified">■</span> {match.missing.length} missing
          </p>
        </div>
      </div>
      )}

      {match.missing.length > 0 && (
        <section className="mt-5">
          <h3 className="font-medium text-ink">
            {match.has_cv
              ? "Missing: learn these, then add a project to prove them"
              : "Skills this job asks for"}
          </h3>
          <ul className="mt-2 flex flex-col gap-2">
            {match.missing.map((item) => (
              <li
                key={`${item.skill_id}-${item.name}`}
                className="flex flex-col gap-2 rounded-md border border-line px-3 py-2 text-sm"
              >
                <span className="flex flex-wrap items-center gap-2">
                  {item.skill_id === null ? (
                    <span className="font-medium text-ink">{item.name}</span>
                  ) : (
                    <Link href={`/skills/${item.skill_id}`} className="font-medium text-ink hover:underline">
                      {item.name}
                    </Link>
                  )}
                  <span className="rounded bg-ground px-1.5 py-0.5 text-xs text-ink-soft">
                    {item.is_required ? "required" : "nice to have"}
                  </span>
                  {item.skill_id === null && (
                    <button
                      type="button"
                      disabled={adding !== null}
                      onClick={() => addSkill(item.name)}
                      className="text-xs text-accent underline disabled:opacity-50"
                    >
                      {adding === item.name ? "Adding…" : "Add to my skills"}
                    </button>
                  )}
                </span>
                {item.skill_id !== null && learning[item.skill_id] ? (
                  <LearnLinks learning={learning[item.skill_id]} />
                ) : item.skill_id === null ? (
                  <span className="flex flex-wrap gap-2">
                    <a
                      href={youtubeSearch(`${item.name} full course tutorial`)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded border border-line px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
                    >
                      Technical / Practical
                    </a>
                    <a
                      href={youtubeSearch(`${item.name} interview questions`)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="rounded border border-line px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
                    >
                      Theory / Interview
                    </a>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      {match.on_cv.length > 0 && (
        <section className="mt-5">
          <h3 className="font-medium text-ink">On your CV, not proven yet</h3>
          <p className="text-xs text-ink-soft">Link a project as evidence on the skill&apos;s page to prove it.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {match.on_cv.map((item) => (
              <Chip key={`${item.skill_id}-${item.name}`} item={item} tone="cv" />
            ))}
          </div>
        </section>
      )}

      {match.proven.length > 0 && (
        <section className="mt-5">
          <h3 className="font-medium text-ink">Proven</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {match.proven.map((item) => (
              <Chip key={`${item.skill_id}-${item.name}`} item={item} tone="proven" />
            ))}
          </div>
        </section>
      )}
      {error && <p className="mt-3 text-sm text-not-verified">{error}</p>}
    </Card>
  );
}
