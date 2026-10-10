"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiDelete, apiGet, apiPost, ApiError } from "@/lib/api";
import GapList from "@/components/GapList";
import NotInSkillsYet from "@/components/NotInSkillsYet";
import SkillSuggestions from "@/components/SkillSuggestions";
import ApplicationEditor from "@/components/ApplicationEditor";
import StatusBadge from "@/components/StatusBadge";
import { Button, ButtonLink, Card, EmptyState, Page, SectionHeading } from "@/components/ui";
import { isWebLink } from "@/lib/links";
import type {
  ComparisonResult,
  ExtractionResponse,
  ExtractorInfo,
  Gap,
  JobDescription,
  Skill,
  SkillSuggestion,
} from "@/lib/types";

type Loaded = {
  status: "loaded";
  job: JobDescription;
  results: ComparisonResult[];
  gaps: Gap[];
  dismissed: Skill[];
  reader: ExtractorInfo;
  suggestions: SkillSuggestion[];
};

type PageState = { status: "loading" } | { status: "error"; message: string } | Loaded;

async function fetchJob(id: number): Promise<Loaded> {
  const [job, results, gaps, dismissed, reader, suggestions] = await Promise.all([
    apiGet<JobDescription>(`/job-descriptions/${id}`),
    apiGet<ComparisonResult[]>(`/job-descriptions/${id}/results`),
    apiGet<Gap[]>(`/job-descriptions/${id}/gaps`),
    apiGet<Skill[]>(`/job-descriptions/${id}/dismissed`),
    apiGet<ExtractorInfo>("/job-descriptions/extractor"),
    apiGet<SkillSuggestion[]>(`/job-descriptions/${id}/suggestions`),
  ]);
  return { status: "loaded", job, results, gaps, dismissed, reader, suggestions };
}

function readerLabel(reader: ExtractorInfo): string {
  if (reader.name === "ollama") return `your skill list + local AI (${reader.model}, free)`;
  if (reader.name === "claude") return "Claude (paid)";
  return "your skill list";
}

// One line summing up a "Look for new skills" run.
function lookSummary(found: ExtractionResponse): string {
  const parts: string[] = [];
  if (found.accepted.length > 0) {
    const names = found.accepted.map((r) => r.skill_name ?? r.requirement_text).join(", ");
    parts.push(
      `Found ${found.accepted.length} new requirement${found.accepted.length === 1 ? "" : "s"}: ${names}.`,
    );
  }
  if (found.linked.length > 0) {
    const names = found.linked.map((r) => r.skill_name ?? r.requirement_text).join(", ");
    parts.push(`Linked to your skills: ${names}.`);
  }
  parts.push("Compared automatically.");
  if (found.note) parts.push(found.note);
  return parts.join(" ");
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Could not reach the backend.";
}


export default function JobDescriptionPage() {
  const params = useParams<{ id: string }>();
  const jobId = Number(params.id);
  const [state, setState] = useState<PageState>({ status: "loading" });
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [lookMessage, setLookMessage] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const router = useRouter();

  async function handleDelete() {
    if (
      !window.confirm(
        "Delete this job? Its requirements and comparison history go with it. " +
          "Your skills, claims and evidence are not affected.",
      )
    ) {
      return;
    }
    setDeleteError(null);
    try {
      await apiDelete(`/job-descriptions/${jobId}`);
      router.push("/job-descriptions");
    } catch (error) {
      setDeleteError(errorMessage(error));
    }
  }

  useEffect(() => {
    let active = true;
    fetchJob(jobId)
      .then((loaded) => active && setState(loaded))
      .catch((error) => active && setState({ status: "error", message: errorMessage(error) }));
    return () => {
      active = false;
    };
  }, [jobId]);

  // Re-checks every requirement against what the user can prove NOW. Older results
  // stay stored; the page then shows the newest one per requirement.
  async function handleCompareAgain() {
    setCompareError(null);
    setComparing(true);
    try {
      await apiPost(`/job-descriptions/${jobId}/compare`, {});
      setState(await fetchJob(jobId));
    } catch (error) {
      setCompareError(errorMessage(error));
    } finally {
      setComparing(false);
    }
  }

  // Re-reads the posting for skills saved since it was analyzed. Only NEW requirements
  // are added (existing ones and their results are never touched), then the job is
  // compared so they get a status right away. Asks first if the reader would be the
  // paid Claude API (only when an ANTHROPIC_API_KEY is configured).
  async function handleLookForNew() {
    setCompareError(null);
    setLookMessage(null);
    setComparing(true);
    try {
      const extractor = await apiGet<ExtractorInfo>("/job-descriptions/extractor");
      if (
        extractor.paid &&
        !window.confirm("This uses the paid Claude API and will cost money. Continue?")
      ) {
        return;
      }
      const found = await apiPost<ExtractionResponse>(`/job-descriptions/${jobId}/extract-new`, {});
      if (found.accepted.length === 0 && found.linked.length === 0) {
        setLookMessage(
          "No new skills found in this posting. Save the skill (or its nickname) on the Skills page first." +
            (found.note ? ` ${found.note}` : ""),
        );
        return;
      }
      await apiPost(`/job-descriptions/${jobId}/compare`, {});
      setState(await fetchJob(jobId));
      setLookMessage(lookSummary(found));
    } catch (error) {
      setCompareError(errorMessage(error));
    } finally {
      setComparing(false);
    }
  }

  // Removes one requirement with its own comparison results; the rest of the job,
  // and everything outside it, stays. Its skill is remembered as "not for this job",
  // so re-reading the posting skips it until "Allow again".
  async function handleRemoveRequirement(requirementId: number, label: string) {
    if (
      !window.confirm(
        `Remove the requirement "${label}" from this job? Its comparison results go with it, ` +
          "and \"Look for new skills\" won't add it back unless you allow it again.",
      )
    ) {
      return;
    }
    setCompareError(null);
    setLookMessage(null);
    setComparing(true);
    try {
      await apiDelete(`/job-descriptions/${jobId}/requirements/${requirementId}`);
      setState(await fetchJob(jobId));
    } catch (error) {
      setCompareError(errorMessage(error));
    } finally {
      setComparing(false);
    }
  }

  // Saves a skill the posting mentions (only its name: no claim, no status), then looks
  // again so the skill-less requirement is linked to it and compared.
  async function handleAddSkill(name: string) {
    await apiPost<Skill>("/skills", { name, category: null });
    await handleLookForNew();
  }

  // Deletes only the "not for this job" note; the next "Look for new skills" may find it.
  async function handleAllowAgain(skill: Skill) {
    setCompareError(null);
    setLookMessage(null);
    setComparing(true);
    try {
      await apiDelete(`/job-descriptions/${jobId}/dismissed/${skill.id}`);
      setState(await fetchJob(jobId));
      setLookMessage(`${skill.name} is allowed again. Click "Look for new skills" to add it back.`);
    } catch (error) {
      setCompareError(errorMessage(error));
    } finally {
      setComparing(false);
    }
  }

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
        <Link href="/job-descriptions" className="mt-2 inline-block text-sm underline">
          Back to job descriptions
        </Link>
      </Page>
    );
  }

  const { job, results, gaps, dismissed, reader } = state;
  // Short skill-less lines are skill names (the local AI reader stores them that way);
  // a long sentence, e.g. from the Claude reader, isn't offered as a skill name.
  const skillless = job.requirements.filter(
    (r) => r.skill_id === null && r.requirement_text.length <= 60,
  );
  const resultByRequirement = new Map(results.map((r) => [r.job_requirement_id, r] as const));
  const lastCompared = results.reduce<string | null>(
    (latest, r) => (latest === null || r.created_at > latest ? r.created_at : latest),
    null,
  );

  return (
    <Page>
      <Link href="/job-descriptions" className="text-sm text-ink-soft hover:text-ink">
        ← All job descriptions
      </Link>

      <div className="mt-3 flex flex-col gap-6">
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="font-display text-3xl text-ink">{job.title ?? "Untitled job"}</h1>
              <p className="mt-1 text-sm text-ink-soft">
                {job.company ?? "No company"} · added {new Date(job.created_at).toLocaleDateString()}
                {job.source_url &&
                  (isWebLink(job.source_url) ? (
                    <>
                      {" · "}
                      <a
                        href={job.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline"
                      >
                        original posting
                      </a>
                    </>
                  ) : (
                    ` · ${job.source_url}`
                  ))}
              </p>
            </div>
            <ButtonLink href={`/job-descriptions/${jobId}/prep`} variant="primary">
              Interview prep →
            </ButtonLink>
          </div>
          <div className="mt-5 border-t border-line pt-4">
            <h2 className="mb-3 font-medium text-ink">Your application</h2>
            <ApplicationEditor
              job={job}
              onSaved={(updated) =>
                setState((prev) => (prev.status === "loaded" ? { ...prev, job: updated } : prev))
              }
            />
          </div>
        </Card>

        <Card>
          <SectionHeading
            title="Requirements"
            hint={
              <>
                {lastCompared
                  ? `Last compared ${new Date(lastCompared).toLocaleString()}. Proved a skill since? Compare again to update.`
                  : "Not compared yet."}
                <span className="block text-xs">Read with {readerLabel(reader)}.</span>
              </>
            }
            actions={
              <>
                <Button
                  onClick={handleLookForNew}
                  disabled={comparing}
                  title="Re-read this posting for skills you've saved since it was analyzed"
                >
                  Look for new skills
                </Button>
                {job.requirements.length > 0 && (
                  <Button variant="primary" onClick={handleCompareAgain} disabled={comparing}>
                    {comparing ? "Working…" : "Compare again"}
                  </Button>
                )}
              </>
            }
          />
          {compareError && <p className="mt-3 text-sm text-not-verified">{compareError}</p>}
          {lookMessage && (
            <p className="mt-3 rounded-md bg-accent-soft px-3 py-2 text-sm text-ink">{lookMessage}</p>
          )}

          {job.requirements.length === 0 ? (
            <div className="mt-4">
              <EmptyState>
                No requirements yet. They come from skills (and nicknames) you&apos;ve saved on the{" "}
                <Link href="/skills" className="underline">
                  Skills
                </Link>{" "}
                page. Save the ones this posting mentions, then click &ldquo;Look for new skills&rdquo;.
              </EmptyState>
            </div>
          ) : (
            <ul className="mt-4 flex flex-col gap-2">
              {job.requirements.map((requirement) => {
                const result = resultByRequirement.get(requirement.id);
                return (
                  <li
                    key={requirement.id}
                    className="flex flex-wrap items-center gap-3 rounded-md border border-line px-3 py-2 text-sm text-ink"
                  >
                    <span className="font-medium">{requirement.requirement_text}</span>
                    {result ? (
                      <StatusBadge status={result.knowledge_status} />
                    ) : (
                      <span className="text-xs text-ink-soft">not compared yet</span>
                    )}
                    {requirement.skill_id !== null ? (
                      <Link href={`/skills/${requirement.skill_id}`} className="text-ink-soft underline">
                        {requirement.skill_name}
                      </Link>
                    ) : (
                      <span className="text-ink-soft">not mapped to a skill</span>
                    )}
                    <Button
                      size="sm"
                      disabled={comparing}
                      className="ml-auto"
                      onClick={() =>
                        handleRemoveRequirement(
                          requirement.id,
                          requirement.skill_name ?? requirement.requirement_text,
                        )
                      }
                    >
                      Remove
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}

          <NotInSkillsYet requirements={skillless} busy={comparing} onAdd={handleAddSkill} />

          {/* Common skills the posting names that you haven't saved (no AI). Adding one
              looks again, so it becomes a requirement and is compared. */}
          <div className="mt-4">
            <SkillSuggestions
              suggestions={state.suggestions}
              where="in this posting"
              busy={comparing}
              onAdded={handleLookForNew}
            />
          </div>

          {dismissed.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2 rounded-lg bg-ground/60 px-4 py-3 text-sm text-ink-soft">
              <span>Removed from this job:</span>
              {dismissed.map((skill) => (
                <span
                  key={skill.id}
                  className="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-0.5 text-ink"
                >
                  {skill.name}
                  <button
                    type="button"
                    disabled={comparing}
                    onClick={() => handleAllowAgain(skill)}
                    className="text-xs text-accent underline disabled:opacity-50"
                  >
                    Allow again
                  </button>
                </span>
              ))}
            </div>
          )}
        </Card>

        {job.requirements.length > 0 && (
          <Card>
            <SectionHeading
              title="Gaps"
              hint="Requirements you can't fully prove yet, with CV status and ways to learn."
            />
            <GapList gaps={gaps} />
          </Card>
        )}

        <Card>
          <details>
            <summary className="cursor-pointer text-sm font-medium text-ink">Original posting text</summary>
            <p className="mt-3 whitespace-pre-wrap rounded-md bg-ground/60 p-3 text-sm text-ink">
              {job.raw_text}
            </p>
          </details>
        </Card>

        <section className="rounded-lg border border-not-verified/40 bg-surface p-5 print:hidden">
          <h2 className="font-display text-lg text-not-verified">Danger zone</h2>
          <h3 className="mt-3 font-medium text-ink">Delete this job</h3>
          <p className="mt-1 text-sm text-ink-soft">
            Removes the job with its requirements and comparison history. Your skills, claims,
            evidence and CV marks stay exactly as they are.
          </p>
          <Button variant="danger" onClick={handleDelete} className="mt-3">
            Delete job
          </Button>
          {deleteError && <p className="mt-2 text-sm text-not-verified">{deleteError}</p>}
        </section>
      </div>
    </Page>
  );
}
