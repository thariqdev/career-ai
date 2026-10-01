"use client";

import { useState, type FormEvent } from "react";
import { apiPatch, ApiError } from "@/lib/api";
import type { Skill } from "@/lib/types";

/**
 * The skill's name and category, with an Edit form (PATCH /skills/{id}). Claims,
 * evidence and everything else follow a rename, since they point at the skill itself.
 * The backend refuses a blank name (422) or one already used by any skill name or
 * nickname (409), and its message is shown as-is. onSaved lets the page reload, since
 * other parts (e.g. YouTube search links) are built from the name.
 */
export default function SkillNameEditor({
  skill,
  onSaved,
}: {
  skill: Skill;
  onSaved: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(skill.name);
  const [category, setCategory] = useState(skill.category ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEdit() {
    setName(skill.name);
    setCategory(skill.category ?? "");
    setError(null);
    setEditing(true);
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await apiPatch<Skill>(`/skills/${skill.id}`, { name, category });
      setEditing(false);
      await onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <div className="flex flex-wrap items-baseline gap-3">
        <div>
          <h1 className="font-display text-2xl text-ink">{skill.name}</h1>
          <p className="mt-1 text-sm text-ink-soft">{skill.category ?? "No category"}</p>
        </div>
        <button
          type="button"
          onClick={startEdit}
          className="rounded border border-line px-2 py-0.5 text-xs text-ink-soft"
        >
          Edit name / category
        </button>
      </div>
    );
  }

  const input = "rounded border border-line bg-surface px-3 py-1.5 text-ink";
  return (
    <form onSubmit={handleSave} className="flex flex-col gap-2 rounded border border-line p-3">
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col text-sm text-ink-soft">
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required className={input} />
        </label>
        <label className="flex flex-col text-sm text-ink-soft">
          Category (optional)
          <input value={category} onChange={(e) => setCategory(e.target.value)} className={input} />
        </label>
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-accent px-3 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="rounded border border-line px-3 py-1.5 text-sm text-ink"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-sm text-not-verified">{error}</p>}
    </form>
  );
}
