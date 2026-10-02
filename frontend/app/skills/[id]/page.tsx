"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/api";
import AliasEditor from "@/components/AliasEditor";
import EvidenceForm, { type EvidenceBody } from "@/components/EvidenceForm";
import LearningPathChecklist from "@/components/LearningPathChecklist";
import LearningProgressControl from "@/components/LearningProgressControl";
import MergeSkillControl from "@/components/MergeSkillControl";
import SkillNameEditor from "@/components/SkillNameEditor";
import StatusBadge from "@/components/StatusBadge";
import { Button, Card, EmptyState, Page, Pill, SectionHeading, inputClasses } from "@/components/ui";
import { cvBadgeClasses, cvBadgeLabel } from "@/lib/cv";
import { MODE_LABEL } from "@/lib/learning";
import { educationLabel, projectLabel, workLabel } from "@/lib/profile";
import type {
  CVStatusResponse,
  Education,
  Evidence,
  LearningModeResources,
  LearningPath,
  LearningProgress,
  LearningProgressStatus,
  Project,
  Skill,
  SkillLearningResources,
  UserSkill,
  WorkExperience,
} from "@/lib/types";

// The four real statuses a claim can be set to, in a fixed display order.
const STATUS_OPTIONS = ["verified", "partial", "provisional", "not_verified"] as const;

// One learning mode's column. Holds its own add-link form state, so the two
// columns' forms never interfere with each other.
function LearningColumn({
  entry,
  busy,
  onAdd,
  onRemove,
}: {
  entry: LearningModeResources;
  busy: boolean;
  onAdd: (title: string, url: string) => Promise<void>;
  onRemove: (resourceId: number) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await onAdd(title, url);
      setTitle("");
      setUrl("");
    } catch (err) {
      // e.g. the backend's 422 for a non-http(s) link, or 409 for a duplicate.
      setError(err instanceof ApiError ? err.message : "Could not save this link.");
    }
  }

  async function handleRemove(resourceId: number) {
    setError(null);
    try {
      await onRemove(resourceId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove this link.");
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-line bg-ground/40 p-4">
      <h3 className="font-medium text-ink">{MODE_LABEL[entry.mode]}</h3>
      <a
        href={entry.search_url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 self-start rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-accent hover:border-accent"
      >
        ▶ Search YouTube: &ldquo;{entry.search_query}&rdquo;
      </a>

      {entry.resources.length === 0 ? (
        <p className="text-sm text-ink-soft">No saved links yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {entry.resources.map((resource) => (
            <li key={resource.id} className="flex items-center justify-between gap-2 text-sm">
              <a
                href={resource.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-ink underline"
              >
                {resource.title}
              </a>
              <Button size="sm" disabled={busy} onClick={() => handleRemove(resource.id)}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-2 border-t border-line pt-3">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          placeholder="Title"
          className={inputClasses}
        />
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          placeholder="https://…"
          className={inputClasses}
        />
        <Button type="submit" variant="primary" disabled={busy} className="self-start">
          Save link
        </Button>
        {error && <p className="text-sm text-not-verified">{error}</p>}
      </form>
    </div>
  );
}

// One piece of evidence: type, title, source and description, with its action buttons.
function EvidenceRow({
  item,
  source,
  showDescription,
  children,
}: {
  item: Evidence;
  source: string | null;
  showDescription: boolean;
  children: ReactNode;
}) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2 text-sm">
      <div className="min-w-0">
        <span className="mr-2 rounded bg-ground px-1.5 py-0.5 font-mono text-xs text-ink-soft">
          {item.evidence_type}
        </span>
        <span className="font-medium text-ink">{item.title}</span>
        {source && <span className="text-ink-soft"> · {source}</span>}
        {showDescription && item.description && (
          <p className="mt-1 text-ink-soft">{item.description}</p>
        )}
      </div>
      <span className="flex gap-2">{children}</span>
    </li>
  );
}

type Loaded = {
  status: "loaded";
  skill: Skill;
  skills: Skill[];
  cvStatus: CVStatusResponse;
  userSkill: UserSkill | null;
  evidence: Evidence[];
  learning: SkillLearningResources;
  progress: LearningProgressStatus;
  projects: Project[];
  works: WorkExperience[];
  educations: Education[];
  path: LearningPath;
};

type PageState = { status: "loading" } | { status: "error"; message: string } | Loaded;

// "from project FundsApp" / "from Engineer at Acme" / "from BSc, State University",
// or null when the evidence has no source (or the source can't be found).
function evidenceSource(item: Evidence, page: Loaded): string | null {
  if (item.project_id !== null) {
    const p = page.projects.find((x) => x.id === item.project_id);
    return p ? `from project ${projectLabel(p)}` : null;
  }
  if (item.work_experience_id !== null) {
    const w = page.works.find((x) => x.id === item.work_experience_id);
    return w ? `from ${workLabel(w)}` : null;
  }
  if (item.education_id !== null) {
    const e = page.educations.find((x) => x.id === item.education_id);
    return e ? `from ${educationLabel(e)}` : null;
  }
  return null;
}

// Everything this page shows, as a finished state (never throws). The requests
// don't depend on each other, so they run in parallel. No GET /skills/{id} exists,
// so the one skill is found by scanning the full list.
async function fetchSkillPage(skillId: number): Promise<PageState> {
  try {
    const [skills, cvStatus, userSkills, evidence, learning, allProgress, projects, works, educations, path] =
      await Promise.all([
        apiGet<Skill[]>("/skills"),
        apiGet<CVStatusResponse>(`/skills/${skillId}/cv-status`),
        apiGet<UserSkill[]>("/user-skills"),
        apiGet<Evidence[]>("/evidence"),
        apiGet<SkillLearningResources>(`/skills/${skillId}/learning-resources`),
        apiGet<LearningProgress[]>("/learning-progress"),
        apiGet<Project[]>("/projects"),
        apiGet<WorkExperience[]>("/work-experiences"),
        apiGet<Education[]>("/educations"),
        apiGet<LearningPath>(`/skills/${skillId}/learning-path`),
      ]);
    const skill = skills.find((s) => s.id === skillId);
    if (!skill) return { status: "error", message: `Skill ${skillId} not found.` };
    return {
      status: "loaded",
      skill,
      skills,
      cvStatus,
      userSkill: userSkills.find((us) => us.skill_id === skillId) ?? null,
      evidence,
      learning,
      progress: allProgress.find((p) => p.skill_id === skillId)?.status ?? "not_started",
      projects,
      works,
      educations,
      path,
    };
  } catch (error) {
    return {
      status: "error",
      message: error instanceof ApiError ? error.message : "Could not reach the backend.",
    };
  }
}

export default function SkillDetailPage() {
  const params = useParams<{ id: string }>();
  const skillId = Number(params.id);

  const [state, setState] = useState<PageState>({ status: "loading" });
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const router = useRouter();
  const [statusError, setStatusError] = useState<string | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [editingEvidenceId, setEditingEvidenceId] = useState<number | null>(null);

  // Refresh after an action. The page stays on screen until the new data arrives,
  // instead of flashing back to "Loading…".
  async function loadAll() {
    setState(await fetchSkillPage(skillId));
  }

  // Fetch first, then set state only in the promise callback: no synchronous
  // setState inside the effect (react-hooks/set-state-in-effect).
  useEffect(() => {
    let active = true;
    fetchSkillPage(skillId).then((next) => active && setState(next));
    return () => {
      active = false;
    };
  }, [skillId]);

  // Refetches only the learning-resources part, so saving or removing a link
  // doesn't send the whole page back to "Loading…".
  async function reloadLearning() {
    const learning = await apiGet<SkillLearningResources>(
      `/skills/${skillId}/learning-resources`,
    );
    setState((prev) => (prev.status === "loaded" ? { ...prev, learning } : prev));
  }

  async function handleAddResource(
    mode: LearningModeResources["mode"],
    title: string,
    url: string,
  ) {
    setBusy(true);
    try {
      await apiPost(`/skills/${skillId}/learning-resources`, { mode, title, url });
      await reloadLearning();
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteSkill() {
    if (state.status !== "loaded") return;
    if (!window.confirm(`Delete "${state.skill.name}"? This can't be undone.`)) return;
    setDeleteError(null);
    setBusy(true);
    try {
      await apiDelete(`/skills/${skillId}`);
      router.push("/skills");
    } catch (error) {
      // e.g. the backend's 409: '"Python" can't be deleted because it is claimed.'
      setDeleteError(error instanceof ApiError ? error.message : "Could not delete the skill.");
      setBusy(false);
    }
  }

  async function handleRemoveResource(resourceId: number) {
    setBusy(true);
    try {
      await apiDelete(`/learning-resources/${resourceId}`);
      await reloadLearning();
    } finally {
      setBusy(false);
    }
  }

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

  // The backend refuses (409) while past job comparisons cite the claim, and its
  // message names those jobs; the evidence itself is always kept.
  async function handleRemoveClaim() {
    if (state.status !== "loaded" || state.userSkill === null) return;
    const confirmed = window.confirm(
      `Remove your claim on "${state.skill.name}"? Its status and evidence links are removed; ` +
        "your evidence itself stays on your profile, and the skill stays in your list.",
    );
    if (!confirmed) return;
    setStatusError(null);
    setBusy(true);
    try {
      await apiDelete(`/user-skills/${state.userSkill.id}`);
      await loadAll();
    } catch (error) {
      setStatusError(error instanceof ApiError ? error.message : "Could not remove the claim.");
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

  // No client-side check for "last evidence of a verified skill": the backend refuses
  // it (409) and its message tells the user to change the status first.
  async function handleUnlinkEvidence(evidenceId: number) {
    if (state.status !== "loaded" || state.userSkill === null) return;
    setLinkError(null);
    setBusy(true);
    try {
      await apiDelete<UserSkill>(`/user-skills/${state.userSkill.id}/evidence-links/${evidenceId}`);
      await loadAll();
    } catch (error) {
      setLinkError(error instanceof ApiError ? error.message : "Could not unlink this evidence.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteEvidence(item: Evidence) {
    if (!window.confirm(`Delete the evidence "${item.title}"? This can't be undone.`)) return;
    setLinkError(null);
    setBusy(true);
    try {
      await apiDelete(`/evidence/${item.id}`);
      await loadAll();
    } catch (error) {
      // e.g. 409: it's part of a past comparison result.
      setLinkError(error instanceof ApiError ? error.message : "Could not delete this evidence.");
    } finally {
      setBusy(false);
    }
  }

  // Errors propagate to EvidenceForm, which shows the backend's message. Creating
  // evidence and linking it stay two distinct, visible actions, matching how the
  // backend keeps POST /evidence and POST /user-skills/{id}/evidence-links separate.
  async function createEvidence(body: EvidenceBody) {
    await apiPost("/evidence", body);
    await loadAll();
  }

  // Never changes the skill's verification status (the backend doesn't either).
  async function updateEvidence(evidenceId: number, body: EvidenceBody) {
    await apiPatch(`/evidence/${evidenceId}`, body);
    setEditingEvidenceId(null);
    await loadAll();
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
      <Page>
        <p className="text-ink-soft">Loading…</p>
      </Page>
    );
  }

  if (state.status === "error") {
    return (
      <Page>
        <p className="text-not-verified">Error: {state.message}</p>
      </Page>
    );
  }

  const { skill, cvStatus, userSkill, evidence } = state;
  const editorFor = (item: Evidence) => (
    <EvidenceForm
      heading="Edit evidence"
      submitLabel="Save"
      initial={item}
      projects={state.projects}
      works={state.works}
      educations={state.educations}
      onSubmit={(body) => updateEvidence(item.id, body)}
      onCancel={() => setEditingEvidenceId(null)}
    />
  );
  const linkedEvidence = userSkill
    ? evidence.filter((e) => userSkill.evidence_ids.includes(e.id))
    : [];
  const unlinkedEvidence = userSkill
    ? evidence.filter((e) => !userSkill.evidence_ids.includes(e.id))
    : [];

  return (
    <Page>
      <div className="flex flex-col gap-6">
        <Card>
          <SkillNameEditor skill={skill} onSaved={loadAll} />
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-ink-soft">
            <span className="flex items-center gap-2">
              Knowledge <StatusBadge status={cvStatus.knowledge_status} />
            </span>
            <span className="flex items-center gap-2">
              CV
              <button
                type="button"
                onClick={handleToggleCvPresence}
                disabled={busy}
                title="Click to toggle CV presence"
                className={`cursor-pointer rounded px-2 py-0.5 font-mono text-xs disabled:opacity-50 ${cvBadgeClasses(cvStatus.cv_status)}`}
              >
                {cvBadgeLabel(cvStatus.cv_status)}
              </button>
            </span>
          </div>
        </Card>

        <LearningPathChecklist path={state.path} />

        <Card>
          {userSkill === null ? (
            <>
              <SectionHeading
                title="Your claim"
                hint="Claim the skill to set its status and link proof to it."
              />
              <EmptyState>You haven&apos;t claimed this skill yet.</EmptyState>
              <Button variant="primary" onClick={handleClaim} disabled={busy} className="mt-3">
                Claim this skill
              </Button>
            </>
          ) : (
            <div className="flex flex-col gap-6">
              <section>
                <SectionHeading
                  title="Your claim"
                  hint="Verified and partial need linked evidence; the app checks."
                  actions={
                    <Button size="sm" variant="danger" disabled={busy} onClick={handleRemoveClaim}>
                      Remove claim
                    </Button>
                  }
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  {STATUS_OPTIONS.map((option) => (
                    <Pill
                      key={option}
                      selected={userSkill.status === option}
                      disabled={busy}
                      onClick={() => handleSetStatus(option)}
                    >
                      {option.replace("_", " ")}
                    </Pill>
                  ))}
                </div>
                {statusError && <p className="mt-2 text-sm text-not-verified">{statusError}</p>}
              </section>

              <section className="border-t border-line pt-5">
                <h3 className="font-medium text-ink">Linked evidence</h3>
                {linkedEvidence.length === 0 ? (
                  <p className="mt-2 text-sm text-ink-soft">No evidence linked yet.</p>
                ) : (
                  <ul className="mt-3 flex flex-col gap-2">
                    {linkedEvidence.map((item) =>
                      editingEvidenceId === item.id ? (
                        <li key={item.id}>{editorFor(item)}</li>
                      ) : (
                        <EvidenceRow
                          key={item.id}
                          item={item}
                          source={evidenceSource(item, state)}
                          showDescription
                        >
                          <Button size="sm" disabled={busy} onClick={() => setEditingEvidenceId(item.id)}>
                            Edit
                          </Button>
                          <Button size="sm" disabled={busy} onClick={() => handleUnlinkEvidence(item.id)}>
                            Unlink
                          </Button>
                        </EvidenceRow>
                      ),
                    )}
                  </ul>
                )}

                {unlinkedEvidence.length > 0 && (
                  <div className="mt-5">
                    <h3 className="font-medium text-ink">Your other evidence</h3>
                    <ul className="mt-2 flex flex-col gap-2">
                      {unlinkedEvidence.map((item) =>
                        editingEvidenceId === item.id ? (
                          <li key={item.id}>{editorFor(item)}</li>
                        ) : (
                          <EvidenceRow
                            key={item.id}
                            item={item}
                            source={evidenceSource(item, state)}
                            showDescription={false}
                          >
                            <Button
                              size="sm"
                              variant="primary"
                              disabled={busy}
                              onClick={() => handleLinkEvidence(item.id)}
                            >
                              Link
                            </Button>
                            <Button size="sm" disabled={busy} onClick={() => setEditingEvidenceId(item.id)}>
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              disabled={busy}
                              onClick={() => handleDeleteEvidence(item)}
                            >
                              Delete
                            </Button>
                          </EvidenceRow>
                        ),
                      )}
                    </ul>
                  </div>
                )}
                {linkError && <p className="mt-2 text-sm text-not-verified">{linkError}</p>}

                <div className="mt-5">
                  <EvidenceForm
                    heading="Add new evidence"
                    submitLabel="Add evidence"
                    projects={state.projects}
                    works={state.works}
                    educations={state.educations}
                    onSubmit={createEvidence}
                  />
                </div>
              </section>
            </div>
          )}
        </Card>

        {/* Reload after a progress change so "Your path" ticks its steps too. */}
        <LearningProgressControl
          skillId={skill.id}
          status={state.progress}
          verified={cvStatus.knowledge_status === "verified"}
          onChange={() => loadAll()}
        />

        <Card>
          <SectionHeading
            title="Learning resources"
            hint="YouTube searches open YouTube itself; saved links are your own picks."
          />
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {state.learning.modes.map((entry) => (
              <LearningColumn
                key={entry.mode}
                entry={entry}
                busy={busy}
                onAdd={(title, url) => handleAddResource(entry.mode, title, url)}
                onRemove={handleRemoveResource}
              />
            ))}
          </div>
        </Card>

        <AliasEditor
          skill={skill}
          onChange={(updated) =>
            setState((prev) => (prev.status === "loaded" ? { ...prev, skill: updated } : prev))
          }
        />

        <section className="rounded-lg border border-not-verified/40 bg-surface p-5">
          <h2 className="font-display text-lg text-not-verified">Danger zone</h2>
          <p className="mt-0.5 text-sm text-ink-soft">These change or remove the skill itself.</p>
          <div className="mt-4 flex flex-col gap-6">
            <MergeSkillControl
              skill={skill}
              skills={state.skills}
              busy={busy}
              onMerged={(target) => router.push(`/skills/${target.id}`)}
            />
            <div className="border-t border-line pt-5">
              <h3 className="font-medium text-ink">Delete this skill</h3>
              <p className="mt-1 text-sm text-ink-soft">
                Only possible while nothing uses it: no claim, no job requirements, not marked on
                your CV, no saved links, no learning progress. Its nicknames are deleted with it.
              </p>
              <Button variant="danger" disabled={busy} onClick={handleDeleteSkill} className="mt-3">
                Delete skill
              </Button>
              {deleteError && <p className="mt-2 text-sm text-not-verified">{deleteError}</p>}
            </div>
          </div>
        </section>
      </div>
    </Page>
  );
}
