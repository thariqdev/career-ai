"use client";

import { useState } from "react";
import Link from "next/link";
import { apiPostForm, ApiError } from "@/lib/api";
import { Button, Card, SectionHeading } from "@/components/ui";
import { useConfirm } from "@/components/ConfirmDialog";

type Preview = { counts: Record<string, number>; problems: string[]; app_empty: boolean };

type State =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "previewed"; file: File; preview: Preview }
  | { status: "restoring"; file: File; preview: Preview }
  | { status: "restored"; counts: Record<string, number> };

const LABELS: Record<string, string> = {
  skills: "skills",
  nicknames: "nicknames",
  claims: "claims",
  evidence: "pieces of evidence",
  projects: "projects",
  work_experiences: "jobs (work)",
  educations: "education entries",
  job_descriptions: "job postings",
  requirements: "requirements",
  comparison_results: "comparison results",
  cv_marks: "CV marks",
  learning_progress: "learning progress entries",
  learning_resources: "saved links",
};

function formFor(file: File): FormData {
  const form = new FormData();
  form.append("file", file);
  return form;
}

function CountList({ counts }: { counts: Record<string, number> }) {
  const nonZero = Object.entries(counts).filter(([, n]) => n > 0);
  if (nonZero.length === 0) return <p className="text-sm text-ink-soft">The file is empty.</p>;
  return (
    <ul className="flex flex-wrap gap-2 text-sm">
      {nonZero.map(([key, n]) => (
        <li key={key} className="rounded-full border border-line bg-surface px-3 py-0.5 text-ink">
          {n} {LABELS[key] ?? key}
        </li>
      ))}
    </ul>
  );
}

// Step 1: choose a file and preview it (the backend writes nothing). Step 2: restore,
// which the backend only allows into an empty app, all or nothing.
export default function RestoreFromBackup() {
  const [state, setState] = useState<State>({ status: "idle" });
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  async function handleChoose(file: File | null) {
    setError(null);
    if (file === null) {
      setState({ status: "idle" });
      return;
    }
    setState({ status: "checking" });
    try {
      const preview = await apiPostForm<Preview>("/import/preview", formFor(file));
      setState({ status: "previewed", file, preview });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
      setState({ status: "idle" });
    }
  }

  async function handleRestore(file: File, preview: Preview) {
    const ok = await confirm({
      title: "Restore this backup?",
      message: "Everything in the file is added to Career AI. It only works on an empty app.",
      confirmLabel: "Restore",
    });
    if (!ok) return;
    setError(null);
    setState({ status: "restoring", file, preview });
    try {
      const result = await apiPostForm<{ counts: Record<string, number> }>("/import", formFor(file));
      setState({ status: "restored", counts: result.counts });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not restore the backup.");
      setState({ status: "previewed", file, preview });
    }
  }

  const previewed = state.status === "previewed" || state.status === "restoring" ? state : null;
  const canRestore =
    previewed !== null && previewed.preview.problems.length === 0 && previewed.preview.app_empty;

  return (
    <Card>
      <SectionHeading
        title="Restore from backup"
        hint="Load a file made by “Download my data”. It's checked first, and only restores into an empty app (after a reset or on a new computer), so nothing you already have is overwritten."
      />

      {state.status === "restored" ? (
        <div className="mt-4 flex flex-col gap-3">
          <p className="font-medium text-verified">✓ Restored.</p>
          <CountList counts={state.counts} />
          <Link href="/" className="text-sm text-accent underline">
            Go to the Dashboard
          </Link>
        </div>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          <input
            type="file"
            accept=".json,application/json"
            onChange={(e) => handleChoose(e.target.files?.[0] ?? null)}
            disabled={state.status === "checking" || state.status === "restoring"}
            className="rounded-md border border-dashed border-line bg-ground/40 px-3 py-3 text-sm text-ink file:mr-3 file:rounded-md file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-sm file:text-surface"
          />
          {state.status === "checking" && <p className="text-sm text-ink-soft">Checking the file…</p>}

          {previewed && (
            <>
              <CountList counts={previewed.preview.counts} />
              {previewed.preview.problems.length > 0 && (
                <div className="rounded-md bg-not-verified-bg px-3 py-2 text-sm text-not-verified">
                  <p className="font-medium">This file can&apos;t be restored:</p>
                  <ul className="ml-4 mt-1 list-disc">
                    {previewed.preview.problems.map((problem) => (
                      <li key={problem}>{problem}</li>
                    ))}
                  </ul>
                </div>
              )}
              {previewed.preview.problems.length === 0 && !previewed.preview.app_empty && (
                <p className="rounded-md bg-warm-soft px-3 py-2 text-sm text-ink">
                  The file looks good, but this app already has data. Restore only works on an
                  empty app, so nothing you have is overwritten or merged by guesswork.
                </p>
              )}
              <Button
                variant="primary"
                className="self-start"
                disabled={!canRestore || state.status === "restoring"}
                onClick={() => handleRestore(previewed.file, previewed.preview)}
              >
                {state.status === "restoring" ? "Restoring…" : "Restore"}
              </Button>
            </>
          )}
        </div>
      )}
      {error && <p className="mt-3 text-sm text-not-verified">{error}</p>}
    </Card>
  );
}
