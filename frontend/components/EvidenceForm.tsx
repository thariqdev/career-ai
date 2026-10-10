"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Button, FieldError, inputClasses, invalidClasses } from "@/components/ui";
import { isWebAddress } from "@/lib/draftValidation";
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
  const [titleError, setTitleError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const badTitle = title.trim() === "" ? "Title is required." : null;
    const badUrl = url.trim() !== "" && !isWebAddress(url) ? "Link must start with http:// or https://." : null;
    setTitleError(badTitle);
    setUrlError(badUrl);
    if (badTitle || badUrl) return;
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

  const input = inputClasses;

  return (
    <form
      noValidate
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-lg border border-line bg-ground/50 p-4"
    >
      <h3 className="font-medium text-ink">{heading}</h3>
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
        <input
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            setTitleError(null);
          }}
          aria-invalid={titleError !== null}
          className={`${input} ${titleError ? invalidClasses : ""}`}
        />
        <FieldError message={titleError} />
      </label>
      <label className="flex flex-col text-sm text-ink-soft">
        Description (optional)
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={input} />
      </label>
      <label className="flex flex-col text-sm text-ink-soft">
        Link (optional)
        <input
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setUrlError(null);
          }}
          placeholder="https://…"
          aria-invalid={urlError !== null}
          className={`${input} ${urlError ? invalidClasses : ""}`}
        />
        <FieldError message={urlError} />
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
        <Button type="submit" variant="primary" disabled={saving}>
          {saving ? "Saving…" : submitLabel}
        </Button>
        {onCancel && <Button onClick={onCancel}>Cancel</Button>}
      </div>
      {error && <p className="text-sm text-not-verified">{error}</p>}
    </form>
  );
}
