"use client";

import { useState, type FormEvent } from "react";
import { apiPatch, apiPost, apiPostForm, ApiError } from "@/lib/api";
import { Button, Card, EmptyState, SectionHeading, inputClasses } from "@/components/ui";
import type { ProfileDrafts } from "@/lib/types";
import { validateEntry, type FieldRule } from "@/lib/draftValidation";

type Kind = "work_experiences" | "educations" | "projects";

type FieldDef = FieldRule;

// Each kind: where it's saved (the normal add endpoint) and its editable fields.
const KINDS: { kind: Kind; title: string; path: string; label: (v: Values) => string; fields: FieldDef[] }[] = [
  {
    kind: "work_experiences",
    title: "Work experience",
    path: "/work-experiences",
    label: (v) => [v.role, v.company].filter(Boolean).join(" at ") || "Untitled job",
    fields: [
      { key: "role", label: "Role", type: "text", required: true },
      { key: "company", label: "Company", type: "text", required: true },
      { key: "start_date", label: "Start", type: "date", required: true },
      { key: "end_date", label: "End (empty = current)", type: "date" },
      { key: "description", label: "What you did", type: "textarea" },
    ],
  },
  {
    kind: "educations",
    title: "Education",
    path: "/educations",
    label: (v) => [v.degree, v.institution].filter(Boolean).join(", ") || "Untitled education",
    fields: [
      { key: "institution", label: "School", type: "text", required: true },
      { key: "degree", label: "Degree", type: "text" },
      { key: "field_of_study", label: "Field of study", type: "text" },
      { key: "start_date", label: "Start", type: "date" },
      { key: "end_date", label: "End", type: "date" },
      { key: "description", label: "Notes", type: "textarea" },
    ],
  },
  {
    kind: "projects",
    title: "Projects",
    path: "/projects",
    label: (v) => v.name || "Untitled project",
    fields: [
      { key: "name", label: "Name", type: "text", required: true },
      { key: "url", label: "Link", type: "text" },
      { key: "start_date", label: "Start", type: "date" },
      { key: "end_date", label: "End", type: "date" },
      { key: "description", label: "What it was", type: "textarea" },
    ],
  },
];

type Values = Record<string, string>;
type Draft = {
  key: string;
  kind: Kind;
  values: Values;
  selected: boolean;
  duplicate: boolean;
  datesText: string | null;
  error: string | null; // a refusal from the server, in plain words
  fieldErrors: Record<string, string>; // problems found before sending, per box
};

function toDrafts(result: ProfileDrafts): Draft[] {
  return KINDS.flatMap(({ kind, fields }) =>
    (result[kind] as unknown as Record<string, unknown>[]).map((d, i) => ({
      key: `${kind}-${i}`,
      kind,
      values: Object.fromEntries(fields.map((f) => [f.key, (d[f.key] as string | null) ?? ""])),
      selected: !(d.duplicate as boolean),
      duplicate: d.duplicate as boolean,
      datesText: d.dates_text as string | null,
      error: null,
      fieldErrors: {},
    })),
  );
}

/**
 * "Fill from my CV": read a CV into draft projects, jobs and education, let the user
 * edit and tick them, then save each through the normal add endpoint (so every rule
 * applies, exactly like typing by hand). Nothing is saved before "Save selected", and
 * the CV itself is never stored. onSaved lets the page refresh its lists.
 */
export default function CvAutofill({ onSaved }: { onSaved: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [cvName, setCvName] = useState<string | null>(null); // the name at the top of the CV

  async function handleRead(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setReading(true);
    try {
      const form = new FormData();
      if (file) form.append("file", file);
      else form.append("text", pasted);
      const result = await apiPostForm<ProfileDrafts>("/profile/cv-drafts", form);
      setCvName(result.name);
      setDrafts(toDrafts(result));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
    } finally {
      setReading(false);
    }
  }

  function update(key: string, change: Partial<Draft> | ((d: Draft) => Partial<Draft>)) {
    setDrafts((prev) =>
      prev === null
        ? prev
        : prev.map((d) => (d.key === key ? { ...d, ...(typeof change === "function" ? change(d) : change) } : d)),
    );
  }

  // Editing a box clears its own message (and any server note on that entry).
  function setValue(draft: Draft, key: string, value: string) {
    update(draft.key, (d) => {
      const fieldErrors = { ...d.fieldErrors };
      delete fieldErrors[key];
      return { values: { ...d.values, [key]: value }, fieldErrors, error: null };
    });
  }

  async function handleUseName() {
    if (cvName === null) return;
    setError(null);
    try {
      await apiPatch("/me", { full_name: cvName });
      setMessage(`✓ Saved your name as ${cvName}.`);
      setCvName(null);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
    }
  }

  async function handleSave() {
    if (drafts === null) return;
    setMessage(null);
    setError(null);

    // Check every ticked entry first; if any box needs fixing, send nothing yet.
    let problems = 0;
    const checked = drafts.map((d) => {
      if (!d.selected) return d;
      const fieldErrors = validateEntry(d.values, KINDS.find((k) => k.kind === d.kind)!.fields);
      problems += Object.keys(fieldErrors).length > 0 ? 1 : 0;
      return { ...d, fieldErrors };
    });
    if (problems > 0) {
      setDrafts(checked);
      setError(
        `${problems} ${problems === 1 ? "entry needs" : "entries need"} a fix before saving. ` +
          "See the red notes, or untick an entry to skip it.",
      );
      return;
    }

    setSaving(true);
    let saved = 0;
    const remaining: Draft[] = [];
    for (const draft of drafts) {
      if (!draft.selected) {
        remaining.push(draft);
        continue;
      }
      const { path, fields } = KINDS.find((k) => k.kind === draft.kind)!;
      const body = Object.fromEntries(
        fields.map((f) => [f.key, draft.values[f.key].trim() === "" ? null : draft.values[f.key].trim()]),
      );
      try {
        await apiPost(path, body);
        saved += 1;
      } catch (err) {
        // e.g. 422 "The end date can't be before the start date." Kept for fixing.
        remaining.push({ ...draft, error: err instanceof ApiError ? err.message : "Could not save." });
      }
    }
    setDrafts(remaining);
    setSaving(false);
    const failed = remaining.filter((d) => d.error).length;
    setMessage(
      `Saved ${saved} ${saved === 1 ? "entry" : "entries"}.` +
        (failed > 0 ? ` ${failed} need${failed === 1 ? "s" : ""} fixing (see the red notes).` : ""),
    );
    if (saved > 0) onSaved();
  }

  const selectedCount = drafts?.filter((d) => d.selected).length ?? 0;

  return (
    <Card>
      <SectionHeading
        title="Fill from my CV"
        hint="Upload your CV and we'll pre-fill your projects, jobs and education for you to check. Nothing is saved until you click Save, and your CV isn't stored."
      />

      {drafts === null ? (
        <form onSubmit={handleRead} className="mt-4 flex flex-col gap-3">
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="rounded-md border border-dashed border-line bg-ground/40 px-3 py-3 text-sm text-ink file:mr-3 file:rounded-md file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-sm file:text-surface"
          />
          <textarea
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            disabled={file !== null}
            rows={3}
            aria-label="CV text"
            placeholder="…or paste your CV text here"
            className={`${inputClasses} disabled:opacity-50`}
          />
          <Button
            type="submit"
            variant="primary"
            className="self-start"
            disabled={reading || (!file && pasted.trim() === "")}
          >
            {reading ? "Reading…" : "Read my CV"}
          </Button>
        </form>
      ) : (
        <div className="mt-4 flex flex-col gap-5">
          {cvName && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-ink">
              <span>
                Name on your CV: <span className="font-medium">{cvName}</span>
              </span>
              <Button onClick={handleUseName}>Use as my name</Button>
            </div>
          )}
          {drafts.length === 0 ? (
            <EmptyState>
              Nothing left to review. Headings like &ldquo;Experience&rdquo;, &ldquo;Education&rdquo; and
              &ldquo;Projects&rdquo; help the reader find entries.
            </EmptyState>
          ) : (
            <p className="rounded-md bg-warm-soft px-3 py-2 text-sm text-ink">
              Please check each entry: the reader copies words from your CV but can put them in the
              wrong box. Dates like &ldquo;Mar 2022&rdquo; become the 1st of that month.
            </p>
          )}

          {KINDS.map(({ kind, title, fields, label }) => {
            const ofKind = drafts.filter((d) => d.kind === kind);
            if (ofKind.length === 0) return null;
            return (
              <section key={kind}>
                <h3 className="font-medium text-ink">
                  {title} ({ofKind.length})
                </h3>
                <ul className="mt-2 flex flex-col gap-3">
                  {ofKind.map((draft) => (
                    <li
                      key={draft.key}
                      className={`rounded-lg border p-3 ${draft.selected ? "border-accent/50 bg-surface" : "border-line bg-ground/40"}`}
                    >
                      <label className="flex cursor-pointer items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={draft.selected}
                          onChange={() => update(draft.key, (d) => ({ selected: !d.selected }))}
                          className="h-4 w-4 accent-accent"
                        />
                        <span className="font-medium text-ink">{label(draft.values)}</span>
                        {draft.datesText && <span className="text-ink-soft">· {draft.datesText}</span>}
                        {draft.duplicate && (
                          <span className="rounded bg-ground px-2 py-0.5 text-xs text-ink-soft">
                            already in your profile
                          </span>
                        )}
                      </label>
                      {draft.selected && (
                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                          {fields.map((f) => (
                            <label
                              key={f.key}
                              className={`flex flex-col gap-1 text-xs text-ink-soft ${f.type === "textarea" ? "sm:col-span-2" : ""}`}
                            >
                              {f.label}
                              {f.required ? " *" : ""}
                              {f.type === "textarea" ? (
                                <textarea
                                  rows={3}
                                  value={draft.values[f.key]}
                                  onChange={(e) => setValue(draft, f.key, e.target.value)}
                                  aria-invalid={f.key in draft.fieldErrors}
                                  className={`${inputClasses} ${f.key in draft.fieldErrors ? "border-not-verified" : ""}`}
                                />
                              ) : (
                                <input
                                  type={f.type}
                                  value={draft.values[f.key]}
                                  onChange={(e) => setValue(draft, f.key, e.target.value)}
                                  aria-invalid={f.key in draft.fieldErrors}
                                  className={`${inputClasses} ${f.key in draft.fieldErrors ? "border-not-verified" : ""}`}
                                />
                              )}
                              {draft.fieldErrors[f.key] && (
                                <span className="text-xs font-medium text-not-verified">
                                  {draft.fieldErrors[f.key]}
                                </span>
                              )}
                            </label>
                          ))}
                        </div>
                      )}
                      {draft.error && <p className="mt-2 text-sm text-not-verified">{draft.error}</p>}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}

          <div className="flex flex-wrap items-center gap-3">
            {drafts.length > 0 && (
              <Button variant="primary" onClick={handleSave} disabled={saving || selectedCount === 0}>
                {saving ? "Saving…" : `Save selected (${selectedCount})`}
              </Button>
            )}
            <Button
              onClick={() => {
                setDrafts(null);
                setMessage(null);
                setFile(null);
                setPasted("");
              }}
            >
              {drafts.length > 0 ? "Cancel" : "Read another CV"}
            </Button>
          </div>
        </div>
      )}
      {message && <p className="mt-3 text-sm text-verified">{message}</p>}
      {error && <p className="mt-3 text-sm text-not-verified">{error}</p>}
    </Card>
  );
}
