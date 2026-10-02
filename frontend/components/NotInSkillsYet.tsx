"use client";

import { useState } from "react";
import Link from "next/link";
import { apiGet, ApiError } from "@/lib/api";
import type { JobRequirement, Skill } from "@/lib/types";

// Requirements with no skill: things the posting names that aren't in your skills yet
// (found by the optional AI reader). "Add skill" saves it, after the same look-alike
// check the Skills page uses, so "Postgres" next to "PostgreSQL" becomes a nickname
// suggestion instead of a duplicate. Nothing is ever added without this click.
export default function NotInSkillsYet({
  requirements,
  busy,
  onAdd,
}: {
  requirements: JobRequirement[];
  busy: boolean;
  onAdd: (name: string) => Promise<void>;
}) {
  const [lookalike, setLookalike] = useState<{ name: string; skill: Skill } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(name: string) {
    setLookalike(null);
    setError(null);
    try {
      const similar = await apiGet<Skill[]>(`/skills/similar?name=${encodeURIComponent(name)}`);
      if (similar.length > 0) {
        setLookalike({ name, skill: similar[0] });
        return;
      }
      await onAdd(name);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the skill.");
    }
  }

  if (requirements.length === 0) return null;

  return (
    <div className="mt-4 rounded border border-line px-3 py-2 text-sm">
      <p className="text-ink">Mentioned in this posting, not in your skills yet:</p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {requirements.map((requirement) => (
          <li
            key={requirement.id}
            className="flex items-center gap-2 rounded border border-line px-2 py-0.5 text-ink"
          >
            {requirement.requirement_text}
            <button
              type="button"
              disabled={busy}
              onClick={() => handleAdd(requirement.requirement_text)}
              className="text-xs text-accent underline disabled:opacity-50"
            >
              Add skill
            </button>
          </li>
        ))}
      </ul>
      {lookalike && (
        <p className="mt-2 text-ink">
          &ldquo;{lookalike.name}&rdquo; looks like{" "}
          <Link href={`/skills/${lookalike.skill.id}`} className="underline">
            {lookalike.skill.name}
          </Link>
          . If it&apos;s the same thing, add it as a nickname there, then click &ldquo;Look for new
          skills&rdquo;.
        </p>
      )}
      {error && <p className="mt-2 text-not-verified">{error}</p>}
      <p className="mt-2 text-xs text-ink-soft">
        Adding a skill only saves its name. It doesn&apos;t claim it or mark it as known.
      </p>
    </div>
  );
}
