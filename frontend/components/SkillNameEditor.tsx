"use client";

import { useState, type FormEvent } from "react";
import { apiPatch, ApiError } from "@/lib/api";
import type { Skill } from "@/lib/types";
import { Button, inputClasses } from "@/components/ui";

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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl text-ink">{skill.name}</h1>
          <p className="mt-1 text-sm text-ink-soft">{skill.category ?? "No category"}</p>
        </div>
        <Button size="sm" onClick={startEdit}>
          Edit name / category
        </Button>
      </div>
    );
  }

  const input = inputClasses;
  return (
    <form onSubmit={handleSave} className="flex flex-col gap-3">
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
        <Button type="submit" variant="primary" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button onClick={() => setEditing(false)}>Cancel</Button>
      </div>
      {error && <p className="text-sm text-not-verified">{error}</p>}
    </form>
  );
}
