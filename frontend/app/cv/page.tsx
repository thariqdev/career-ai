"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { apiPostForm, apiPut, ApiError } from "@/lib/api";
import type { CVPresence, CVScan } from "@/lib/types";
import { Button, Card, EmptyState, Page, SectionHeading, inputClasses } from "@/components/ui";
import SkillSuggestions from "@/components/SkillSuggestions";

// Two steps, matching the backend: scanning only suggests; nothing is saved until
// the user reviews the ticks and clicks Save. The CV itself is never stored.
type PageState =
  | { status: "input" }
  | { status: "scanning" }
  | { status: "review"; scan: CVScan }
  | { status: "saving"; scan: CVScan }
  | { status: "saved"; onCv: number; offCv: number };

export default function CVPage() {
  const [state, setState] = useState<PageState>({ status: "input" });
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Found skills start ticked; "on CV but not found" start unticked, so a skill the
  // reader missed (e.g. a nickname you haven't saved) is never removed by accident.
  const [present, setPresent] = useState<Set<number>>(new Set());
  const [absent, setAbsent] = useState<Set<number>>(new Set());

  function reset() {
    setFile(null);
    setPasted("");
    setError(null);
    setState({ status: "input" });
  }

  async function handleScan(event: FormEvent) {
    event.preventDefault();
    await scan();
  }

  // Also used after adding a suggested skill (rescan = true): the same file or text is
  // scanned again in place, so the new skill appears under "Found on your CV". Ticks the
  // user already changed are kept; newly found skills start ticked.
  async function scan(rescan = false) {
    setError(null);
    const form = new FormData();
    if (file) form.append("file", file);
    else form.append("text", pasted);
    if (!rescan) setState({ status: "scanning" });
    try {
      const result = await apiPostForm<CVScan>("/cv/scan", form);
      setPresent((prev) => {
        const previous = state.status === "review" ? state.scan.found.map((f) => f.skill_id) : [];
        return new Set(
          result.found.map((f) => f.skill_id).filter((id) => prev.has(id) || !previous.includes(id)),
        );
      });
      if (state.status !== "review") setAbsent(new Set());
      setState({ status: "review", scan: result });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
      if (!rescan) setState({ status: "input" });
    }
  }

  async function handleSave(scan: CVScan) {
    setError(null);
    setState({ status: "saving", scan });
    try {
      const saved = await apiPut<CVPresence[]>("/cv/presence", {
        present_skill_ids: [...present],
        absent_skill_ids: [...absent],
      });
      setState({
        status: "saved",
        onCv: saved.filter((s) => s.present).length,
        offCv: saved.filter((s) => !s.present).length,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
      setState({ status: "review", scan });
    }
  }

  function toggle(set: Set<number>, update: (s: Set<number>) => void, id: number) {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    update(next);
  }

  return (
    <Page title="My CV">
      <p className="mt-1 text-sm text-ink-soft">
        Find which of your saved skills your CV mentions. Your CV is read on your own
        computer and is not stored. Being on your CV is never proof of a skill: only
        evidence verifies it.
      </p>

      {(state.status === "input" || state.status === "scanning") && (
        <Card className="mt-6">
          <form onSubmit={handleScan} className="flex flex-col gap-4">
            <label className="flex flex-col gap-2 text-sm text-ink-soft">
              Upload a CV (PDF, Word .docx, or .txt, up to 5 MB)
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="rounded-md border border-dashed border-line bg-ground/40 px-3 py-3 text-sm text-ink file:mr-3 file:rounded-md file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-sm file:text-surface"
              />
            </label>
            <div className="flex items-center gap-3 text-xs uppercase tracking-wide text-ink-soft">
              <span className="h-px flex-1 bg-line" />
              or paste its text
              <span className="h-px flex-1 bg-line" />
            </div>
            <textarea
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              disabled={file !== null}
              rows={6}
              aria-label="CV text"
              placeholder="Paste your CV text here…"
              className={`${inputClasses} disabled:opacity-50`}
            />
            <Button
              type="submit"
              variant="primary"
              disabled={state.status === "scanning" || (!file && pasted.trim() === "")}
              className="self-start"
            >
              {state.status === "scanning" ? "Scanning…" : "Scan"}
            </Button>
          </form>
        </Card>
      )}

      {(state.status === "review" || state.status === "saving") && (
        <div className="mt-6 flex flex-col gap-6">
          <p className="rounded-md bg-accent-soft px-3 py-2 text-sm text-ink">
            Read {state.scan.characters.toLocaleString()} characters. Nothing is saved until
            you click Save.
          </p>

          <Card>
            <SectionHeading title="Found on your CV" hint="Untick any that shouldn't be marked." />
            {state.scan.found.length === 0 ? (
              <div className="mt-3">
                <EmptyState>
                  None of your saved skills were found. Add them (or their nicknames) on the{" "}
                  <Link href="/skills" className="underline">
                    Skills
                  </Link>{" "}
                  page, then scan again.
                </EmptyState>
              </div>
            ) : (
              <ul className="mt-3 flex flex-col gap-2">
                {state.scan.found.map((f) => (
                  <li key={f.skill_id}>
                    <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line px-3 py-2 text-sm text-ink hover:bg-ground/40">
                      <input
                        type="checkbox"
                        checked={present.has(f.skill_id)}
                        onChange={() => toggle(present, setPresent, f.skill_id)}
                        className="h-4 w-4 accent-accent"
                      />
                      <span className="font-medium">{f.skill_name}</span>
                      {f.matched_text.toLowerCase() !== f.skill_name.toLowerCase() && (
                        <span className="text-ink-soft">(found as &ldquo;{f.matched_text}&rdquo;)</span>
                      )}
                      {f.on_cv && <span className="ml-auto text-xs text-ink-soft">already marked</span>}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <SkillSuggestions
            suggestions={state.scan.suggestions}
            where="on your CV"
            busy={state.status === "saving"}
            onAdded={() => scan(true)}
          />

          {state.scan.on_cv_not_found.length > 0 && (
            <Card>
              <SectionHeading
                title="Marked on your CV, but not found in this one"
                hint="Tick any you've removed from your CV. Leave the rest unticked: the reader may just not know the name your CV uses."
              />
              <ul className="mt-3 flex flex-col gap-2">
                {state.scan.on_cv_not_found.map((s) => (
                  <li key={s.skill_id}>
                    <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line px-3 py-2 text-sm text-ink hover:bg-ground/40">
                      <input
                        type="checkbox"
                        checked={absent.has(s.skill_id)}
                        onChange={() => toggle(absent, setAbsent, s.skill_id)}
                        className="h-4 w-4 accent-accent"
                      />
                      Mark {s.skill_name} as not on my CV
                    </label>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="flex gap-3">
            <Button
              variant="primary"
              onClick={() => handleSave(state.scan)}
              disabled={state.status === "saving" || (present.size === 0 && absent.size === 0)}
            >
              {state.status === "saving" ? "Saving…" : "Save"}
            </Button>
            <Button onClick={reset}>Cancel</Button>
          </div>
        </div>
      )}

      {state.status === "saved" && (
        <Card className="mt-6">
          <p className="font-medium text-verified">
            ✓ Saved: {state.onCv} marked on your CV
            {state.offCv > 0 ? `, ${state.offCv} marked not on it` : ""}.
          </p>
          <p className="mt-2 text-sm text-ink-soft">
            See them on the{" "}
            <Link href="/skills" className="underline">
              Skills
            </Link>{" "}
            page, and any CV advice on the{" "}
            <Link href="/" className="underline">
              Dashboard
            </Link>
            .
          </p>
          <Button onClick={reset} className="mt-4">
            Scan another CV
          </Button>
        </Card>
      )}

      {error && <p className="mt-4 text-sm text-not-verified">{error}</p>}
    </Page>
  );
}
