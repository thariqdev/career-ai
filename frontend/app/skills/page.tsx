"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { cvBadgeClasses, cvBadgeLabel } from "@/lib/cv";
import type { CVStatusResponse, Skill } from "@/lib/types";

// One row = one Skill plus its combined knowledge/CV status. Fetched separately
// per skill (see the N+1 note in the component below) rather than in one request,
// because GET /skills/{id}/cv-status doesn't have a "for all skills" version yet.
type Row = { skill: Skill; cvStatus: CVStatusResponse };

type ListState =
  | { status: "loading" }
  | { status: "loaded"; rows: Row[] }
  | { status: "error"; message: string };

async function fetchRow(skill: Skill): Promise<Row> {
  const cvStatus = await apiGet<CVStatusResponse>(`/skills/${skill.id}/cv-status`);
  return { skill, cvStatus };
}

export default function SkillsPage() {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function loadAll() {
    setState({ status: "loading" });
    try {
      const skills = await apiGet<Skill[]>("/skills");
      const rows = await Promise.all(skills.map(fetchRow));
      setState({ status: "loaded", rows });
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Could not reach the backend.";
      setState({ status: "error", message });
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      await apiPost<Skill>("/skills", {
        name,
        category: category.trim() === "" ? null : category,
      });
      setName("");
      setCategory("");
      await loadAll();
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
      if (state.status !== "loaded") return;
      setState({
        status: "loaded",
        rows: state.rows.map((r) => (r.skill.id === row.skill.id ? updated : r)),
      });
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
            onChange={(e) => setName(e.target.value)}
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
