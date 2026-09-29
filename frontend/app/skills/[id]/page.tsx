"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import type { CVStatus, CVStatusResponse, Evidence, Skill, UserSkill } from "@/lib/types";

// The same five EvidenceType values as backend/app/db/models/enums.py, hardcoded
// here — the same small, acceptable duplication StatusBadge already has for
// VerificationStatus (see its own comment). If the backend enum ever changes,
// this list has to change to match, same as everywhere else in this frontend.
const EVIDENCE_TYPES = ["work_experience", "project", "certification", "artifact", "other"] as const;

// The four real statuses a claim can be set to, in a fixed display order.
const STATUS_OPTIONS = ["verified", "partial", "provisional", "not_verified"] as const;

// Same reasoning as app/skills/page.tsx's own cvBadgeClasses/cvBadgeLabel — this is
// the exact same toggle pattern, not reused via import, matching how that page
// itself was written (a small page-local helper, not extracted into a component).
function cvBadgeClasses(status: CVStatus): string {
  switch (status) {
    case "present":
      return "bg-accent-soft text-accent";
    case "missing_from_cv":
      return "bg-warm-soft text-warm";
    case "not_present":
      return "bg-line text-ink-soft";
  }
}

function cvBadgeLabel(status: CVStatus): string {
  return status.replace(/_/g, " ");
}

type Loaded = {
  status: "loaded";
  skill: Skill;
  cvStatus: CVStatusResponse;
  userSkill: UserSkill | null;
  evidence: Evidence[];
};

type PageState = { status: "loading" } | { status: "error"; message: string } | Loaded;

export default function SkillDetailPage() {
  const params = useParams<{ id: string }>();
  const skillId = Number(params.id);

  const [state, setState] = useState<PageState>({ status: "loading" });
  const [busy, setBusy] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [evidenceType, setEvidenceType] = useState<(typeof EVIDENCE_TYPES)[number]>("project");
  const [evidenceTitle, setEvidenceTitle] = useState("");
  const [evidenceDescription, setEvidenceDescription] = useState("");
  const [evidenceFormError, setEvidenceFormError] = useState<string | null>(null);

  async function loadAll() {
    setState({ status: "loading" });
    try {
      // No GET /skills/{id} endpoint exists, so the one skill is found by
      // scanning the full list — the same kind of trade-off already called out
      // as the N+1 pattern on the Skills page, just a different shape of it.
      const skills = await apiGet<Skill[]>("/skills");
      const skill = skills.find((s) => s.id === skillId);
      if (!skill) {
        setState({ status: "error", message: `Skill ${skillId} not found.` });
        return;
      }
      const cvStatus = await apiGet<CVStatusResponse>(`/skills/${skillId}/cv-status`);
      const userSkills = await apiGet<UserSkill[]>("/user-skills");
      const userSkill = userSkills.find((us) => us.skill_id === skillId) ?? null;
      const evidence = await apiGet<Evidence[]>("/evidence");
      setState({ status: "loaded", skill, cvStatus, userSkill, evidence });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not reach the backend.",
      });
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillId]);

  async function handleToggleCvPresence() {
    if (state.status !== "loaded") return;
    setBusy(true);
    try {
      await apiPatch(`/skills/${skillId}/cv-presence`, {
        present: state.cvStatus.cv_status !== "present",
      });
      await loadAll();
    } finally {
      setBusy(false);
    }
  }

  async function handleClaim() {
    setBusy(true);
    try {
      await apiPost<UserSkill>("/user-skills", { skill_id: skillId });
      await loadAll();
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "Could not claim this skill.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleLinkEvidence(evidenceId: number) {
    if (state.status !== "loaded" || state.userSkill === null) return;
    setLinkError(null);
    setBusy(true);
    try {
      await apiPost(`/user-skills/${state.userSkill.id}/evidence-links`, {
        evidence_id: evidenceId,
      });
      await loadAll();
    } catch (error) {
      setLinkError(error instanceof ApiError ? error.message : "Could not link this evidence.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateEvidence(event: FormEvent) {
    event.preventDefault();
    setEvidenceFormError(null);
    setBusy(true);
    try {
      // Creating evidence and linking it stay two distinct, visible actions,
      // matching how the backend itself keeps POST /evidence and
      // POST /user-skills/{id}/evidence-links separate — this does not auto-link.
      await apiPost("/evidence", {
        evidence_type: evidenceType,
        title: evidenceTitle,
        description: evidenceDescription.trim() === "" ? null : evidenceDescription,
      });
      setEvidenceTitle("");
      setEvidenceDescription("");
      await loadAll();
    } catch (error) {
      setEvidenceFormError(
        error instanceof ApiError ? error.message : "Could not create this evidence.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSetStatus(status: (typeof STATUS_OPTIONS)[number]) {
    if (state.status !== "loaded" || state.userSkill === null) return;
    setStatusError(null);
    setBusy(true);
    try {
      // No client-side check for "enough evidence" here on purpose — clicking is
      // always allowed, and the real backend rule (verification_service.set_status)
      // is what accepts or rejects it, so the rule is actually demonstrated live.
      await apiPost(`/user-skills/${state.userSkill.id}/status`, { status });
      await loadAll();
    } catch (error) {
      setStatusError(error instanceof ApiError ? error.message : "Could not change status.");
    } finally {
      setBusy(false);
    }
  }

  if (state.status === "loading") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-ink-soft">Loading…</p>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-8">
        <p className="text-not-verified">Error: {state.message}</p>
      </main>
    );
  }

  const { skill, cvStatus, userSkill, evidence } = state;
  const linkedEvidence = userSkill
    ? evidence.filter((e) => userSkill.evidence_ids.includes(e.id))
    : [];
  const unlinkedEvidence = userSkill
    ? evidence.filter((e) => !userSkill.evidence_ids.includes(e.id))
    : [];

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="font-display text-2xl text-ink">{skill.name}</h1>
      <p className="mt-1 text-sm text-ink-soft">{skill.category ?? "No category"}</p>

      <div className="mt-3 flex items-center gap-3">
        <StatusBadge status={cvStatus.knowledge_status} />
        <button
          type="button"
          onClick={handleToggleCvPresence}
          disabled={busy}
          title="Click to toggle CV presence"
          className={`cursor-pointer rounded px-2 py-0.5 font-mono text-xs disabled:opacity-50 ${cvBadgeClasses(cvStatus.cv_status)}`}
        >
          {cvBadgeLabel(cvStatus.cv_status)}
        </button>
      </div>

      {userSkill === null ? (
        <div className="mt-8">
          <p className="text-ink-soft">You haven&apos;t claimed this skill yet.</p>
          <button
            type="button"
            onClick={handleClaim}
            disabled={busy}
            className="mt-3 rounded bg-accent px-4 py-1.5 text-sm text-surface disabled:opacity-50"
          >
            Claim this skill
          </button>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-8">
          <section>
            <h2 className="font-display text-lg text-ink">Status</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={busy}
                  onClick={() => handleSetStatus(option)}
                  className={`rounded border px-3 py-1.5 text-sm disabled:opacity-50 ${
                    userSkill.status === option
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-line text-ink-soft"
                  }`}
                >
                  {option.replace("_", " ")}
                </button>
              ))}
            </div>
            {statusError && <p className="mt-2 text-sm text-not-verified">{statusError}</p>}
          </section>

          <section>
            <h2 className="font-display text-lg text-ink">Evidence</h2>
            {linkedEvidence.length === 0 ? (
              <p className="mt-2 text-ink-soft">No evidence linked yet.</p>
            ) : (
              <ul className="mt-3 flex flex-col gap-2">
                {linkedEvidence.map((item) => (
                  <li key={item.id} className="rounded border border-line px-3 py-2 text-sm">
                    <span className="font-mono text-xs text-ink-soft">{item.evidence_type}</span>{" "}
                    <span className="text-ink">{item.title}</span>
                    {item.description && (
                      <p className="mt-1 text-ink-soft">{item.description}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {unlinkedEvidence.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm text-ink-soft">Your other evidence</h3>
                <ul className="mt-2 flex flex-col gap-2">
                  {unlinkedEvidence.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between rounded border border-line px-3 py-2 text-sm"
                    >
                      <span>
                        <span className="font-mono text-xs text-ink-soft">{item.evidence_type}</span>{" "}
                        <span className="text-ink">{item.title}</span>
                      </span>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleLinkEvidence(item.id)}
                        className="rounded border border-line px-2 py-1 text-xs text-ink disabled:opacity-50"
                      >
                        Link
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {linkError && <p className="mt-2 text-sm text-not-verified">{linkError}</p>}

            <form
              onSubmit={handleCreateEvidence}
              className="mt-6 flex flex-col gap-3 rounded border border-line p-4"
            >
              <h3 className="text-sm text-ink-soft">Add new evidence</h3>
              <label className="flex flex-col text-sm text-ink-soft">
                Type
                <select
                  value={evidenceType}
                  onChange={(e) => setEvidenceType(e.target.value as (typeof EVIDENCE_TYPES)[number])}
                  className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
                >
                  {EVIDENCE_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col text-sm text-ink-soft">
                Title
                <input
                  value={evidenceTitle}
                  onChange={(e) => setEvidenceTitle(e.target.value)}
                  required
                  className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
                />
              </label>
              <label className="flex flex-col text-sm text-ink-soft">
                Description (optional)
                <textarea
                  value={evidenceDescription}
                  onChange={(e) => setEvidenceDescription(e.target.value)}
                  className="rounded border border-line bg-surface px-3 py-1.5 text-ink"
                />
              </label>
              <button
                type="submit"
                disabled={busy}
                className="self-start rounded bg-accent px-4 py-1.5 text-sm text-surface disabled:opacity-50"
              >
                Add evidence
              </button>
              {evidenceFormError && (
                <p className="text-sm text-not-verified">{evidenceFormError}</p>
              )}
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
