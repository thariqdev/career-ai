"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { apiPostForm, apiPut, ApiError } from "@/lib/api";
import type { CVPresence, CVScan } from "@/lib/types";

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
    setError(null);
    const form = new FormData();
    if (file) form.append("file", file);
    else form.append("text", pasted);
    setState({ status: "scanning" });
    try {
      const scan = await apiPostForm<CVScan>("/cv/scan", form);
      setPresent(new Set(scan.found.map((f) => f.skill_id)));
      setAbsent(new Set());
      setState({ status: "review", scan });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
      setState({ status: "input" });
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
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-ink">My CV</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Find which of your saved skills your CV mentions. Your CV is read on your own
        computer and is not stored. Being on your CV is never proof of a skill: only
        evidence verifies it.
      </p>

      {(state.status === "input" || state.status === "scanning") && (
        <form onSubmit={handleScan} className="mt-6 flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm text-ink-soft">
            Upload a CV (PDF, Word .docx, or .txt, up to 5 MB)
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-ink"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink-soft">
            …or paste its text
            <textarea
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              disabled={file !== null}
              rows={6}
              className="rounded border border-line bg-surface px-3 py-1.5 text-ink disabled:opacity-50"
            />
          </label>
          <button
            type="submit"
            disabled={state.status === "scanning" || (!file && pasted.trim() === "")}
            className="self-start rounded bg-accent px-4 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            {state.status === "scanning" ? "Scanning…" : "Scan"}
          </button>
        </form>
      )}

      {(state.status === "review" || state.status === "saving") && (
        <div className="mt-6 flex flex-col gap-6">
          <p className="text-sm text-ink-soft">
            Read {state.scan.characters.toLocaleString()} characters. Nothing is saved until
            you click Save.
          </p>

          <section>
            <h2 className="font-display text-lg text-ink">Found on your CV</h2>
            {state.scan.found.length === 0 ? (
              <p className="mt-2 text-sm text-ink-soft">
                None of your saved skills were found. Add them (or their nicknames) on the{" "}
                <Link href="/skills" className="underline">
                  Skills
                </Link>{" "}
                page, then scan again.
              </p>
            ) : (
              <ul className="mt-2 flex flex-col gap-2">
                {state.scan.found.map((f) => (
                  <li key={f.skill_id}>
                    <label className="flex items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={present.has(f.skill_id)}
                        onChange={() => toggle(present, setPresent, f.skill_id)}
                      />
                      {f.skill_name}
                      {f.matched_text.toLowerCase() !== f.skill_name.toLowerCase() && (
                        <span className="text-ink-soft">(found as &ldquo;{f.matched_text}&rdquo;)</span>
                      )}
                      {f.on_cv && <span className="text-xs text-ink-soft">· already marked</span>}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {state.scan.on_cv_not_found.length > 0 && (
            <section>
              <h2 className="font-display text-lg text-ink">
                Marked on your CV, but not found in this one
              </h2>
              <p className="mt-1 text-sm text-ink-soft">
                Tick any you&apos;ve removed from your CV. Leave the rest unticked: the reader
                may just not know the name your CV uses.
              </p>
              <ul className="mt-2 flex flex-col gap-2">
                {state.scan.on_cv_not_found.map((s) => (
                  <li key={s.skill_id}>
                    <label className="flex items-center gap-2 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={absent.has(s.skill_id)}
                        onChange={() => toggle(absent, setAbsent, s.skill_id)}
                      />
                      Mark {s.skill_name} as not on my CV
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => handleSave(state.scan)}
              disabled={state.status === "saving" || (present.size === 0 && absent.size === 0)}
              className="rounded bg-accent px-4 py-1.5 text-sm text-surface disabled:opacity-50"
            >
              {state.status === "saving" ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              onClick={reset}
              className="rounded border border-line px-4 py-1.5 text-sm text-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {state.status === "saved" && (
        <div className="mt-6 flex flex-col gap-3">
          <p className="text-ink">
            Saved: {state.onCv} marked on your CV
            {state.offCv > 0 ? `, ${state.offCv} marked not on it` : ""}.
          </p>
          <p className="text-sm text-ink-soft">
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
          <button
            type="button"
            onClick={reset}
            className="self-start rounded border border-line px-4 py-1.5 text-sm text-ink"
          >
            Scan another CV
          </button>
        </div>
      )}

      {error && <p className="mt-4 text-sm text-not-verified">{error}</p>}
    </main>
  );
}
