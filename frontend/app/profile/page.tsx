"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { dateRange, educationLabel, projectLabel, workLabel } from "@/lib/profile";
import type { Education, Project, WorkExperience } from "@/lib/types";

type Field = {
  key: string;
  label: string;
  type: "text" | "date" | "url" | "textarea";
  required?: boolean;
};

type Item = { id: number; description: string | null };

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Could not reach the backend.";
}

/**
 * One kind of profile record: its list (with Remove) and an add form. The backend
 * enforces every rule (required fields, date order, web-only links, "in use"), and
 * its messages are shown as-is.
 */
function ProfileSection<T extends Item>({
  title,
  hint,
  path,
  fields,
  label,
  details,
}: {
  title: string;
  hint: string;
  path: string;
  fields: Field[];
  label: (item: T) => string;
  details: (item: T) => ReactNode;
}) {
  const [items, setItems] = useState<T[] | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The record being edited, or null when the form adds a new one.
  const [editing, setEditing] = useState<T | null>(null);

  function startEdit(item: T) {
    const record = item as unknown as Record<string, unknown>;
    setValues(Object.fromEntries(fields.map((f) => [f.key, (record[f.key] as string | null) ?? ""])));
    setEditing(item);
    setError(null);
  }

  function cancelEdit() {
    setEditing(null);
    setValues({});
    setError(null);
  }

  // Fetch first, then set state only in the promise callbacks.
  useEffect(() => {
    let active = true;
    apiGet<T[]>(path)
      .then((list) => active && setItems(list))
      .catch((err) => active && setError(errorMessage(err)));
    return () => {
      active = false;
    };
  }, [path]);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Empty optional inputs are sent as null (the backend would treat "" the same
      // for text, but an empty date must be null to be valid at all).
      const body = Object.fromEntries(
        fields.map((f) => [f.key, (values[f.key] ?? "").trim() === "" ? null : values[f.key]]),
      );
      // Editing sends every field (PATCH): an emptied optional field is cleared, and
      // the backend refuses to clear a required one.
      if (editing) await apiPatch(`${path}/${editing.id}`, body);
      else await apiPost(path, body);
      setValues({});
      setEditing(null);
      setItems(await apiGet<T[]>(path));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(item: T) {
    if (!window.confirm(`Remove "${label(item)}"?`)) return;
    setError(null);
    setBusy(true);
    try {
      await apiDelete(`${path}/${item.id}`);
      setItems(await apiGet<T[]>(path));
    } catch (err) {
      // e.g. 409: 'Project "FundsApp" can't be removed because 2 pieces of evidence come from it.'
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-8">
      <h2 className="font-display text-lg text-ink">{title}</h2>
      <p className="mt-1 text-sm text-ink-soft">{hint}</p>

      {items === null && !error && <p className="mt-2 text-sm text-ink-soft">Loading…</p>}
      {items !== null && items.length === 0 && (
        <p className="mt-2 text-sm text-ink-soft">Nothing added yet.</p>
      )}
      {items !== null && items.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-start justify-between gap-3 rounded border border-line px-3 py-2 text-sm"
            >
              <div>
                <p className="text-ink">{label(item)}</p>
                <p className="text-xs text-ink-soft">{details(item)}</p>
                {item.description && <p className="mt-1 text-ink-soft">{item.description}</p>}
              </div>
              <span className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => startEdit(item)}
                  className="rounded border border-line px-2 py-0.5 text-xs text-ink-soft disabled:opacity-50"
                >
                  Edit
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRemove(item)}
                  className="rounded border border-line px-2 py-0.5 text-xs text-ink-soft disabled:opacity-50"
                >
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleAdd} className="mt-4 grid gap-2 rounded border border-line p-3 sm:grid-cols-2">
        {editing && (
          <p className="text-sm text-ink sm:col-span-2">Editing &ldquo;{label(editing)}&rdquo;</p>
        )}
        {fields.map((field) => (
          <label
            key={field.key}
            className={`flex flex-col text-sm text-ink-soft ${field.type === "textarea" ? "sm:col-span-2" : ""}`}
          >
            {field.label}
            {field.required ? " *" : ""}
            {field.type === "textarea" ? (
              <textarea
                value={values[field.key] ?? ""}
                onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                rows={2}
                className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
              />
            ) : (
              <input
                type={field.type === "url" ? "text" : field.type}
                value={values[field.key] ?? ""}
                onChange={(e) => setValues({ ...values, [field.key]: e.target.value })}
                required={field.required}
                placeholder={field.type === "url" ? "https://…" : undefined}
                className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
              />
            )}
          </label>
        ))}
        <div className="flex gap-2 sm:col-span-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-accent px-3 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            {editing ? "Save changes" : "Add"}
          </button>
          {editing && (
            <button
              type="button"
              onClick={cancelEdit}
              className="rounded border border-line px-3 py-1.5 text-sm text-ink"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
      {error && <p className="mt-2 text-sm text-not-verified">{error}</p>}
    </section>
  );
}

export default function ProfilePage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-ink">My Profile</h1>
      <p className="mt-1 text-sm text-ink-soft">
        Your projects, jobs and education, entered by you. Evidence on a skill&apos;s page can
        say which of these it comes from, so your proof points at something real.
      </p>

      <ProfileSection<Project>
        title="Projects"
        hint="Things you've built: side projects, coursework, open source."
        path="/projects"
        fields={[
          { key: "name", label: "Name", type: "text", required: true },
          { key: "role", label: "Your role", type: "text" },
          { key: "url", label: "Link (e.g. GitHub)", type: "url" },
          { key: "start_date", label: "Start", type: "date" },
          { key: "end_date", label: "End", type: "date" },
          { key: "description", label: "What it was", type: "textarea" },
        ]}
        label={projectLabel}
        details={(p) => (
          <>
            {dateRange(p.start_date, p.end_date, "ongoing")}
            {p.url && (
              <>
                {p.start_date || p.end_date ? " · " : ""}
                <a href={p.url} target="_blank" rel="noopener noreferrer" className="underline">
                  link
                </a>
              </>
            )}
          </>
        )}
      />

      <ProfileSection<WorkExperience>
        title="Work experience"
        hint="Jobs and internships. Leave the end date empty for your current job."
        path="/work-experiences"
        fields={[
          { key: "company", label: "Company", type: "text", required: true },
          { key: "role", label: "Role", type: "text", required: true },
          { key: "start_date", label: "Start", type: "date", required: true },
          { key: "end_date", label: "End", type: "date" },
          { key: "description", label: "What you did", type: "textarea" },
        ]}
        label={workLabel}
        details={(w) => dateRange(w.start_date, w.end_date)}
      />

      <ProfileSection<Education>
        title="Education"
        hint="Degrees, diplomas and courses."
        path="/educations"
        fields={[
          { key: "institution", label: "School", type: "text", required: true },
          { key: "degree", label: "Degree", type: "text" },
          { key: "field_of_study", label: "Field of study", type: "text" },
          { key: "start_date", label: "Start", type: "date" },
          { key: "end_date", label: "End", type: "date" },
          { key: "description", label: "Notes", type: "textarea" },
        ]}
        label={educationLabel}
        details={(e) => dateRange(e.start_date, e.end_date)}
      />
    </main>
  );
}
