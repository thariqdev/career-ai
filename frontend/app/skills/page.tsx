"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { Button, Card, EmptyState, FieldError, Page, inputClasses, invalidClasses } from "@/components/ui";
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
  const [nameError, setNameError] = useState<string | null>(null);
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
    if (name.trim() === "") {
      setNameError("Type the skill's name first.");
      return;
    }
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
    <Page title="Skills">
      <p className="mt-1 text-sm text-ink-soft">
        Your skill list. Job postings and your CV are read against these names and nicknames.
        Click a skill to claim it, prove it and plan how to learn it.
      </p>

      <Card className="mt-6">
        <form noValidate onSubmit={handleCreate} className="flex flex-wrap items-start gap-3">
          <label className="flex flex-col gap-1 text-sm text-ink-soft">
            Name
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setLookalikes(null);
                setNameError(null);
              }}
              placeholder="e.g. Kubernetes"
              aria-invalid={nameError !== null}
              className={`${inputClasses} ${nameError ? invalidClasses : ""}`}
            />
            <FieldError message={nameError} />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink-soft">
            Category (optional)
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="e.g. DevOps"
              className={inputClasses}
            />
          </label>
          <Button type="submit" variant="primary" disabled={submitting} className="mt-6">
            {submitting ? "Adding…" : "Add skill"}
          </Button>
        </form>
        {lookalikes && (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-warm/40 bg-warm-soft/60 px-4 py-3 text-sm text-ink">
            <span>
              &ldquo;{name.trim()}&rdquo; looks like <strong>{lookalikes.join(", ")}</strong>.
              {" "}If it&apos;s the same thing, add it as a nickname on that skill&apos;s page instead.
            </span>
            <Button size="sm" onClick={createSkill} disabled={submitting}>
              Add anyway
            </Button>
            <Button size="sm" onClick={() => setLookalikes(null)} className="border-transparent bg-transparent">
              Cancel
            </Button>
          </div>
        )}
        {formError && <p className="mt-2 text-sm text-not-verified">{formError}</p>}
      </Card>

      <div className="mt-6">
        {state.status === "loading" && <p className="text-ink-soft">Loading…</p>}

        {state.status === "error" && <p className="text-not-verified">Error: {state.message}</p>}

        {state.status === "loaded" && state.rows.length === 0 && (
          <EmptyState>No skills yet. Add the ones you know or want to learn above.</EmptyState>
        )}

        {state.status === "loaded" && state.rows.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line bg-ground/60 text-xs uppercase tracking-wide text-ink-soft">
                <tr>
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                  <th className="px-4 py-2 font-medium">Knowledge</th>
                  <th className="px-4 py-2 font-medium">CV</th>
                </tr>
              </thead>
              <tbody>
                {state.rows.map((row) => (
                  <tr key={row.skill.id} className="border-b border-line last:border-b-0 hover:bg-ground/40">
                    <td className="px-4 py-3 text-ink">
                      <Link href={`/skills/${row.skill.id}`} className="font-medium hover:underline">
                        {row.skill.name}
                      </Link>
                      {row.skill.aliases.length > 0 && (
                        <span className="block text-xs text-ink-soft">
                          also: {row.skill.aliases.join(", ")}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-ink-soft">{row.skill.category ?? "—"}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.cvStatus.knowledge_status} />
                    </td>
                    <td className="px-4 py-3">
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
          </div>
        )}
      </div>
    </Page>
  );
}
