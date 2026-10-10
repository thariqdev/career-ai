"use client";

import { useState } from "react";
import Link from "next/link";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { Skill, SkillSuggestion } from "@/lib/types";

/**
 * Common skills a CV or posting mentions that you haven't saved yet (from the
 * backend's fixed catalogue). Nothing is added without a click. "Add" saves the skill
 * with its category, plus the text's own spelling as a nickname when it differs
 * ("JS" for JavaScript), so the next scan or re-read finds it. A look-alike of a skill
 * you already have is pointed out instead of being added twice. onAdded runs after
 * each add, so the page can rescan or re-read.
 */
export default function SkillSuggestions({
  suggestions,
  where,
  busy,
  onAdded,
}: {
  suggestions: SkillSuggestion[];
  where: string; // "on your CV" / "in this posting"
  busy: boolean;
  onAdded: () => Promise<void>;
}) {
  const [adding, setAdding] = useState<string | null>(null);
  const [lookalike, setLookalike] = useState<{ name: string; skill: Skill } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(suggestion: SkillSuggestion) {
    setError(null);
    setLookalike(null);
    setAdding(suggestion.name);
    try {
      const similar = await apiGet<Skill[]>(`/skills/similar?name=${encodeURIComponent(suggestion.name)}`);
      if (similar.length > 0) {
        setLookalike({ name: suggestion.name, skill: similar[0] });
        return;
      }
      const skill = await apiPost<Skill>("/skills", {
        name: suggestion.name,
        category: suggestion.category,
      });
      const ownWords = suggestion.matched_text.trim();
      if (ownWords.toLowerCase() !== suggestion.name.toLowerCase()) {
        await apiPost<Skill>(`/skills/${skill.id}/aliases`, { alias: ownWords });
      }
      await onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the skill.");
    } finally {
      setAdding(null);
    }
  }

  if (suggestions.length === 0) return null;

  return (
    <div className="rounded-lg border border-warm/40 bg-warm-soft/50 px-4 py-3 text-sm">
      <p className="font-medium text-ink">Also {where}, not in your skills yet:</p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <li
            key={s.name}
            className="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-0.5 text-ink"
            title={s.matched_text !== s.name ? `Written as "${s.matched_text}"` : s.category}
          >
            {s.name}
            <button
              type="button"
              disabled={busy || adding !== null}
              onClick={() => handleAdd(s)}
              className="text-xs text-accent underline disabled:opacity-50"
            >
              {adding === s.name ? "Adding…" : "Add"}
            </button>
          </li>
        ))}
      </ul>
      {lookalike && (
        <p className="mt-2 text-ink">
          &ldquo;{lookalike.name}&rdquo; looks like your skill{" "}
          <Link href={`/skills/${lookalike.skill.id}`} className="underline">
            {lookalike.skill.name}
          </Link>
          . If it&apos;s the same thing, add it as a nickname there instead.
        </p>
      )}
      {error && <p className="mt-2 text-not-verified">{error}</p>}
      <p className="mt-2 text-xs text-ink-soft">
        Suggestions come from a fixed list of common skills. Adding one only saves its name:
        it doesn&apos;t claim it or mark it as known.
      </p>
    </div>
  );
}
