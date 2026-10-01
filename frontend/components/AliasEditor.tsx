"use client";

import { useState, type FormEvent } from "react";
import { apiDelete, apiPost, ApiError } from "@/lib/api";
import type { Skill } from "@/lib/types";

/**
 * Lists a skill's aliases ("nicknames") with add and remove. Both endpoints
 * return the updated Skill, which is handed to onChange, so the page updates
 * without refetching. Backend messages (409 collision, 422 blank, 404 missing)
 * are shown as-is.
 */
export default function AliasEditor({
  skill,
  onChange,
}: {
  skill: Skill;
  onChange: (updated: Skill) => void;
}) {
  const [alias, setAlias] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<Skill>) {
    setError(null);
    setBusy(true);
    try {
      onChange(await action());
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update nicknames.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    const added = await run(() => apiPost<Skill>(`/skills/${skill.id}/aliases`, { alias }));
    if (added) setAlias("");
  }

  function handleRemove(text: string) {
    run(() =>
      apiDelete<Skill>(`/skills/${skill.id}/aliases?alias=${encodeURIComponent(text)}`),
    );
  }

  return (
    <section className="mt-6">
      <h2 className="font-display text-lg text-ink">Nicknames</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Other names job postings use for {skill.name}. The requirement reader finds these too.
      </p>

      {skill.aliases.length === 0 ? (
        <p className="mt-2 text-sm text-ink-soft">No nicknames yet.</p>
      ) : (
        <ul className="mt-2 flex flex-wrap gap-2">
          {skill.aliases.map((text) => (
            <li
              key={text}
              className="flex items-center gap-2 rounded border border-line px-2 py-0.5 text-sm text-ink"
            >
              {text}
              <button
                type="button"
                disabled={busy}
                onClick={() => handleRemove(text)}
                aria-label={`Remove nickname ${text}`}
                className="text-xs text-ink-soft hover:text-not-verified disabled:opacity-50"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleAdd} className="mt-3 flex flex-wrap items-center gap-2">
        <input
          value={alias}
          onChange={(e) => setAlias(e.target.value)}
          required
          placeholder="e.g. Postgres"
          className="rounded border border-line bg-surface px-3 py-1.5 text-sm text-ink"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-accent px-3 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          Add nickname
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-not-verified">{error}</p>}
    </section>
  );
}
