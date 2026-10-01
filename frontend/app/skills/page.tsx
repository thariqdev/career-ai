"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { cvBadgeClasses, cvBadgeLabel } from "@/lib/cv";
import type { CVStatusResponse, Skill } from "@/lib/types";

// One row = one Skill plus its combined knowledge/CV status.
type Row = { skill: Skill; cvStatus: CVStatusResponse };

type ListState =
  | { status: "loading" }
  | { status: "loaded"; rows: Row[] }
  | { status: "error"; message: string };

// What GET /skills/{id}/cv-status reports for a skill with no claim and no CV mark.
// GET /cv/status leaves such skills out, so they get this instead.
function untouched(skill: Skill): CVStatusResponse {
  return {
    skill_id: skill.id,
    skill_name: skill.name,
    knowledge_status: null,
    cv_status: "not_present",
    recommendation: null,
  };
}

// Two requests in parallel, however many skills there are (not one per skill).
async function fetchRows(): Promise<Row[]> {
  const [skills, statuses] = await Promise.all([
    apiGet<Skill[]>("/skills"),
    apiGet<CVStatusResponse[]>("/cv/status"),
  ]);
  const bySkillId = new Map(statuses.map((s) => [s.skill_id, s] as const));
  return skills.map((skill) => ({ skill, cvStatus: bySkillId.get(skill.id) ?? untouched(skill) }));
}

// One skill's row, after its CV badge is toggled: still a single request.
async function fetchRow(skill: Skill): Promise<Row> {
  const cvStatus = await apiGet<CVStatusResponse>(`/skills/${skill.id}/cv-status`);
  return { skill, cvStatus };
}

function errorState(error: unknown): ListState {
  return {
    status: "error",
    message: error instanceof ApiError ? error.message : "Could not reach the backend.",
  };
}

export default function SkillsPage() {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Names of existing skills that look like the one being added ("pytho n" -> Python).
  // Non-null means we're waiting for the user to choose "Add anyway" or "Cancel".
  const [lookalikes, setLookalikes] = useState<string[] | null>(null);

  // Refresh after adding a skill. The current list stays on screen until the new
  // one arrives, instead of flashing back to "Loading…".
  async function reload() {
    try {
      setState({ status: "loaded", rows: await fetchRows() });
    } catch (error) {
      setState(errorState(error));
    }
  }

  // Fetch first, then set state only in the promise callbacks: no synchronous
  // setState inside the effect (react-hooks/set-state-in-effect).
  useEffect(() => {
    let active = true;
    fetchRows()
      .then((rows) => active && setState({ status: "loaded", rows }))
      .catch((error) => active && setState(errorState(error)));
    return () => {
      active = false;
    };
  }, []);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      // Only a warning: the user can still choose "Add anyway".
      const similar = await apiGet<Skill[]>(`/skills/similar?name=${encodeURIComponent(name)}`);
      if (similar.length > 0) {
        setLookalikes(similar.map((s) => s.name));
        return;
      }
    } catch {
      // If the check itself fails, don't block adding; the backend still rejects
      // exact duplicates on its own.
    } finally {
      setSubmitting(false);
    }
    await createSkill();
  }

  async function createSkill() {
    setLookalikes(null);
    setFormError(null);
    setSubmitting(true);
    try {
      await apiPost<Skill>("/skills", {
        name,
        category: category.trim() === "" ? null : category,
      });
      setName("");
      setCategory("");
      await reload();
    } catch (error) {
      // Show the backend's own message (e.g. its 409 duplicate-name or 422
      // blank-name text) rather than a generic one.
      setFormError(error instanceof ApiError ? error.message : "Could not create the skill.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggleCvPresence(row: Row) {
    const nextPresent = row.cvStatus.cv_status !== "present";
    try {
      await apiPatch(`/skills/${row.skill.id}/cv-presence`, { present: nextPresent });
      const updated = await fetchRow(row.skill);
      // Functional update: works from the latest rows, so two quick toggles on
      // different skills can't overwrite each other with a stale copy.
      setState((prev) =>
        prev.status === "loaded"
          ? { status: "loaded", rows: prev.rows.map((r) => (r.skill.id === row.skill.id ? updated : r)) }
          : prev,
      );
    } catch {
      // A failed toggle just leaves the row as it was; no separate error banner
      // for this small interaction, in keeping with this page's minimal scope.
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-ink">Skills</h1>

      <form onSubmit={handleCreate} className="mt-6 flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-sm text-ink-soft">
          Name
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setLookalikes(null);
            }}
            required
            className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
          />
        </label>
        <label className="flex flex-col text-sm text-ink-soft">
          Category (optional)
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-accent px-4 py-1.5 text-sm text-surface disabled:opacity-50"
        >
          {submitting ? "Adding…" : "Add skill"}
        </button>
      </form>
      {lookalikes && (
        <div className="mt-3 flex flex-wrap items-center gap-3 rounded border border-warm bg-warm-soft px-3 py-2 text-sm text-ink">
          <span>
            &ldquo;{name.trim()}&rdquo; looks like <strong>{lookalikes.join(", ")}</strong>.
            {" "}If it&apos;s the same thing, add it as a nickname on that skill&apos;s page instead.
          </span>
          <button
            type="button"
            onClick={createSkill}
            disabled={submitting}
            className="rounded border border-line bg-surface px-3 py-1 text-ink disabled:opacity-50"
          >
            Add anyway
          </button>
          <button
            type="button"
            onClick={() => setLookalikes(null)}
            className="rounded px-3 py-1 text-ink-soft hover:text-ink"
          >
            Cancel
          </button>
        </div>
      )}
      {formError && <p className="mt-2 text-sm text-not-verified">{formError}</p>}

      <div className="mt-8">
        {state.status === "loading" && <p className="text-ink-soft">Loading…</p>}

        {state.status === "error" && (
          <p className="text-not-verified">Error: {state.message}</p>
        )}

        {state.status === "loaded" && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-ink-soft">
              <tr>
                <th className="py-2">Name</th>
                <th className="py-2">Category</th>
                <th className="py-2">Knowledge</th>
                <th className="py-2">CV</th>
              </tr>
            </thead>
            <tbody>
              {state.rows.map((row) => (
                <tr key={row.skill.id} className="border-b border-line">
                  <td className="py-2 text-ink">
                    <Link href={`/skills/${row.skill.id}`} className="hover:underline">
                      {row.skill.name}
                    </Link>
                    {row.skill.aliases.length > 0 && (
                      <span className="block text-xs text-ink-soft">
                        also: {row.skill.aliases.join(", ")}
                      </span>
                    )}
                  </td>
                  <td className="py-2 text-ink-soft">{row.skill.category ?? "—"}</td>
                  <td className="py-2">
                    <StatusBadge status={row.cvStatus.knowledge_status} />
                  </td>
                  <td className="py-2">
                    <button
                      type="button"
                      onClick={() => handleToggleCvPresence(row)}
                      title="Click to toggle CV presence"
                      className={`cursor-pointer rounded px-2 py-0.5 font-mono text-xs ${cvBadgeClasses(row.cvStatus.cv_status)}`}
                    >
                      {cvBadgeLabel(row.cvStatus.cv_status)}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
