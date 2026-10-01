"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { educationLabel, projectLabel, workLabel } from "@/lib/profile";
import type { Education, Evidence, Project, WorkExperience } from "@/lib/types";

// The same five EvidenceType values as backend/app/db/models/enums.py, hardcoded here:
// the same small, accepted duplication StatusBadge has for VerificationStatus. If the
// backend enum changes, this list has to change to match.
const EVIDENCE_TYPES = ["work_experience", "project", "certification", "artifact", "other"] as const;

export type EvidenceBody = {
  evidence_type: (typeof EVIDENCE_TYPES)[number];
  title: string;
  description: string | null;
  url: string | null;
  project_id: number | null;
  work_experience_id: number | null;
  education_id: number | null;
};

// "" (no source) or "project:3" / "work:2" / "education:1".
function sourceChoice(evidence?: Evidence): string {
  if (evidence?.project_id != null) return `project:${evidence.project_id}`;
  if (evidence?.work_experience_id != null) return `work:${evidence.work_experience_id}`;
  if (evidence?.education_id != null) return `education:${evidence.education_id}`;
  return "";
}

/**
 * Adding and editing evidence use the same fields. With `initial` it's an edit form,
 * pre-filled; without, an add form that clears itself after saving. Every field is
 * always sent, including all three source ids with at most one set, so switching the
 * source clears the old one in the same request. The backend checks every rule and
 * its message (e.g. a non-web link) is shown as-is.
 */
export default function EvidenceForm({
  heading,
  submitLabel,
  initial,
  projects,
  works,
  educations,
  onSubmit,
  onCancel,
}: {
  heading: string;
  submitLabel: string;
  initial?: Evidence;
  projects: Project[];
  works: WorkExperience[];
  educations: Education[];
  onSubmit: (body: EvidenceBody) => Promise<void>;
  onCancel?: () => void;
}) {
  const [type, setType] = useState<EvidenceBody["evidence_type"]>(
    (initial?.evidence_type as EvidenceBody["evidence_type"]) ?? "project",
  );
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [url, setUrl] = useState(initial?.url ?? "");
  const [source, setSource] = useState(sourceChoice(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    const [kind, id] = source.split(":");
    const sourceId = id ? Number(id) : null;
    try {
      await onSubmit({
        evidence_type: type,
        title,
        description: description.trim() === "" ? null : description,
        url: url.trim() === "" ? null : url,
        project_id: kind === "project" ? sourceId : null,
        work_experience_id: kind === "work" ? sourceId : null,
        education_id: kind === "education" ? sourceId : null,
      });
      if (!initial) {
        setTitle("");
        setDescription("");
        setUrl("");
        setSource("");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save this evidence.");
    } finally {
      setSaving(false);
    }
  }

  const input = "rounded border border-line bg-surface px-3 py-1.5 text-ink";

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border border-line p-4">
      <h3 className="text-sm text-ink-soft">{heading}</h3>
      <label className="flex flex-col text-sm text-ink-soft">
        Type
        <select value={type} onChange={(e) => setType(e.target.value as EvidenceBody["evidence_type"])} className={input}>
          {EVIDENCE_TYPES.map((t) => (
            <option key={t} value={t}>
              {t.replace("_", " ")}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col text-sm text-ink-soft">
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required className={input} />
      </label>
      <label className="flex flex-col text-sm text-ink-soft">
        Description (optional)
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={input} />
      </label>
      <label className="flex flex-col text-sm text-ink-soft">
        Link (optional)
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://…"
          className={input}
        />
      </label>
      <label className="flex flex-col text-sm text-ink-soft">
        Comes from (optional)
        <select value={source} onChange={(e) => setSource(e.target.value)} className={input}>
          <option value="">Nothing specific</option>
          {projects.length > 0 && (
            <optgroup label="Projects">
              {projects.map((p) => (
                <option key={p.id} value={`project:${p.id}`}>
                  {projectLabel(p)}
                </option>
              ))}
            </optgroup>
          )}
          {works.length > 0 && (
            <optgroup label="Work experience">
              {works.map((w) => (
                <option key={w.id} value={`work:${w.id}`}>
                  {workLabel(w)}
                </option>
              ))}
            </optgroup>
          )}
          {educations.length > 0 && (
            <optgroup label="Education">
              {educations.map((e) => (
                <option key={e.id} value={`education:${e.id}`}>
                  {educationLabel(e)}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        {projects.length + works.length + educations.length === 0 && (
          <span className="mt-1 text-xs">
            Add projects, jobs or education on{" "}
            <Link href="/profile" className="underline">
              My Profile
            </Link>{" "}
            to pick them here.
          </span>
        )}
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-accent px-4 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          {saving ? "Saving…" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="rounded border border-line px-4 py-1.5 text-sm text-ink">
            Cancel
          </button>
        )}
      </div>
      {error && <p className="text-sm text-not-verified">{error}</p>}
    </form>
  );
}
