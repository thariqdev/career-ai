"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import { Button, Card, EmptyState, FieldError, Page, SectionHeading, inputClasses, invalidClasses } from "@/components/ui";
import { validateEntry } from "@/lib/draftValidation";
import DownloadMyData from "@/components/DownloadMyData";
import RestoreFromBackup from "@/components/RestoreFromBackup";
import CvAutofill from "@/components/CvAutofill";
import { useConfirm } from "@/components/ConfirmDialog";
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
  reloadKey,
}: {
  reloadKey: number; // bumped after "Fill from my CV" saves, so the list refetches
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
  const confirm = useConfirm();
  // Problems found when the button is clicked, per box (shown under each box).
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  function setValue(key: string, value: string) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function startEdit(item: T) {
    const record = item as unknown as Record<string, unknown>;
    setValues(Object.fromEntries(fields.map((f) => [f.key, (record[f.key] as string | null) ?? ""])));
    setEditing(item);
    setError(null);
    setFieldErrors({});
  }

  function cancelEdit() {
    setEditing(null);
    setValues({});
    setError(null);
    setFieldErrors({});
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
  }, [path, reloadKey]);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const problems = validateEntry(values, fields);
    setFieldErrors(problems);
    if (Object.keys(problems).length > 0) return; // nothing is sent until it's fixed
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
    const ok = await confirm({
      title: `Remove "${label(item)}"?`,
      message: "It will be removed from your profile. Evidence that comes from it must be removed first.",
      confirmLabel: "Remove",
      danger: true,
    });
    if (!ok) return;
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
    <Card>
      <SectionHeading title={title} hint={hint} />

      {items === null && !error && <p className="mt-3 text-sm text-ink-soft">Loading…</p>}
      {items !== null && items.length === 0 && (
        <div className="mt-3">
          <EmptyState>Nothing added yet.</EmptyState>
        </div>
      )}
      {items !== null && items.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-start justify-between gap-3 rounded-md border border-line px-3 py-2 text-sm"
            >
              <div>
                <p className="font-medium text-ink">{label(item)}</p>
                <p className="text-xs text-ink-soft">{details(item)}</p>
                {item.description && <p className="mt-1 text-ink-soft">{item.description}</p>}
              </div>
              <span className="flex gap-2">
                <Button size="sm" disabled={busy} onClick={() => startEdit(item)}>
                  Edit
                </Button>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => handleRemove(item)}>
                  Remove
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <form
        noValidate
        onSubmit={handleAdd}
        className="mt-4 grid gap-3 rounded-lg border border-line bg-ground/50 p-4 sm:grid-cols-2"
      >
        <p className="font-medium text-ink sm:col-span-2">
          {editing ? <>Editing &ldquo;{label(editing)}&rdquo;</> : `Add to ${title.toLowerCase()}`}
        </p>
        {fields.map((field) => (
          <label
            key={field.key}
            className={`flex flex-col gap-1 text-sm text-ink-soft ${field.type === "textarea" ? "sm:col-span-2" : ""}`}
          >
            {field.label}
            {field.required ? " *" : ""}
            {field.type === "textarea" ? (
              <textarea
                value={values[field.key] ?? ""}
                onChange={(e) => setValue(field.key, e.target.value)}
                rows={2}
                aria-invalid={field.key in fieldErrors}
                className={`${inputClasses} ${field.key in fieldErrors ? invalidClasses : ""}`}
              />
            ) : (
              <input
                type={field.type === "url" ? "text" : field.type}
                value={values[field.key] ?? ""}
                onChange={(e) => setValue(field.key, e.target.value)}
                placeholder={field.type === "url" ? "https://…" : undefined}
                aria-invalid={field.key in fieldErrors}
                className={`${inputClasses} ${field.key in fieldErrors ? invalidClasses : ""}`}
              />
            )}
            <FieldError message={fieldErrors[field.key]} />
          </label>
        ))}
        <div className="flex gap-2 sm:col-span-2">
          <Button type="submit" variant="primary" disabled={busy}>
            {editing ? "Save changes" : "Add"}
          </Button>
          {editing && <Button onClick={cancelEdit}>Cancel</Button>}
        </div>
      </form>
      {error && <p className="mt-2 text-sm text-not-verified">{error}</p>}
    </Card>
  );
}

export default function ProfilePage() {
  const [reloadKey, setReloadKey] = useState(0);
  return (
    <Page title="My Profile">
      <p className="mt-1 text-sm text-ink-soft">
        Your projects, jobs and education, entered by you. Evidence on a skill&apos;s page can
        say which of these it comes from, so your proof points at something real.
      </p>

      <div className="mt-6 flex flex-col gap-6">
        <CvAutofill onSaved={() => setReloadKey((k) => k + 1)} />


        <ProfileSection<Project>
          reloadKey={reloadKey}
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
          reloadKey={reloadKey}
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
          reloadKey={reloadKey}
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

        <DownloadMyData />
        <RestoreFromBackup />
      </div>
    </Page>
  );
}
