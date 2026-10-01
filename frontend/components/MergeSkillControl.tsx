"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { Skill } from "@/lib/types";

// Look-alikes of this skill ("pytho n" -> Python), excluding itself. Never throws:
// the hint is optional, so a failed check just shows no suggestion.
async function fetchLookalikes(skillId: number, name: string): Promise<Skill[]> {
  try {
    const similar = await apiGet<Skill[]>(`/skills/similar?name=${encodeURIComponent(name)}`);
    return similar.filter((s) => s.id !== skillId);
  } catch {
    return [];
  }
}

// "Merge into another skill": folds THIS skill (the duplicate) into the chosen one.
// The backend does all the moving and refuses when both skills are claimed; this only
// picks the target, confirms, and reports the backend's message.
export default function MergeSkillControl({
  skill,
  skills,
  busy,
  onMerged,
}: {
  skill: Skill;
  skills: Skill[];
  busy: boolean;
  onMerged: (target: Skill) => void;
}) {
  const [lookalikes, setLookalikes] = useState<Skill[]>([]);
  const [chosen, setChosen] = useState<string>("");
  const [merging, setMerging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch first, then set state only in the promise callback (react-hooks/set-state-in-effect).
  // Keyed on id and name, so a page refresh (a new but equal skill object) doesn't refetch.
  const { id: skillId, name: skillName } = skill;
  useEffect(() => {
    let active = true;
    fetchLookalikes(skillId, skillName).then((found) => active && setLookalikes(found));
    return () => {
      active = false;
    };
  }, [skillId, skillName]);

  const others = skills.filter((s) => s.id !== skill.id);
  // A look-alike is suggested until the user picks something themselves.
  const targetId = chosen !== "" ? chosen : lookalikes[0] ? String(lookalikes[0].id) : "";
  const target = others.find((s) => String(s.id) === targetId) ?? null;

  async function handleMerge() {
    if (target === null) return;
    const confirmed = window.confirm(
      `Merge "${skill.name}" into "${target.name}"? Everything attached to "${skill.name}" ` +
        `moves to "${target.name}", "${skill.name}" becomes one of its nicknames, and ` +
        `"${skill.name}" is removed. This can't be undone.`,
    );
    if (!confirmed) return;
    setError(null);
    setMerging(true);
    try {
      onMerged(await apiPost<Skill>(`/skills/${skill.id}/merge-into/${target.id}`, {}));
    } catch (err) {
      // e.g. the backend's 409 when both skills are claimed.
      setError(err instanceof ApiError ? err.message : "Could not merge the skills.");
      setMerging(false);
    }
  }

  if (others.length === 0) return null;

  return (
    <section className="mt-12 border-t border-line pt-6">
      <h2 className="font-display text-lg text-ink">Merge into another skill</h2>
      <p className="mt-1 text-sm text-ink-soft">
        For a duplicate of a skill you already have. Job requirements, nicknames, your claim
        and its evidence, saved links, learning progress and the CV mark all move to the other
        skill. If both skills are claimed, remove the claim you don&apos;t want first.
      </p>
      {lookalikes.length > 0 && (
        <p className="mt-2 text-sm text-ink">
          This looks like <strong>{lookalikes.map((s) => s.name).join(", ")}</strong>.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={targetId}
          onChange={(e) => setChosen(e.target.value)}
          className="rounded border border-line bg-surface px-3 py-1.5 text-sm text-ink"
        >
          <option value="">Choose a skill…</option>
          {others.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy || merging || target === null}
          onClick={handleMerge}
          className="rounded border border-line px-3 py-1.5 text-sm text-ink disabled:opacity-50"
        >
          {merging ? "Merging…" : "Merge"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-not-verified">{error}</p>}
    </section>
  );
}
