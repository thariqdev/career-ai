/**
 * Shared TypeScript types matching backend/app/core/models.py's response shapes.
 * Field names and nullability are copied exactly — if the backend schema changes,
 * this file should change to match, not the other way around.
 */

export type Skill = {
  id: number;
  name: string;
  category: string | null;
  aliases: string[];
};

export type CVStatus = "present" | "missing_from_cv" | "not_present";

export type CVStatusResponse = {
  skill_id: number;
  skill_name: string;
  knowledge_status: string | null;
  cv_status: CVStatus;
  recommendation: string | null;
};

// Matches backend UserResponse. Not asked for by name in this task, but needed by
// both the home page's existing proof code and the new header's user chip.
export type User = {
  id: number;
  email: string;
  full_name: string | null;
};

// Matches backend JobDescriptionResponse/JobRequirementResponse/ExtractionResponse.
export type JobRequirement = {
  id: number;
  requirement_text: string;
  is_required: boolean;
  skill_id: number | null;
  skill_name: string | null;
  created_at: string;
};

// Matches backend ApplicationStatus: where your application for a job stands.
export type ApplicationStatus =
  | "saved"
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export type JobDescription = {
  id: number;
  title: string | null;
  company: string | null;
  source_url: string | null;
  raw_text: string;
  created_at: string;
  application_status: ApplicationStatus;
  applied_on: string | null; // YYYY-MM-DD
  application_notes: string | null;
  next_interview_at: string | null; // ISO time (stored as UTC)
  requirements: JobRequirement[];
};

// Matches backend LearningPathResponse.
export type PathStep = {
  key: "start" | "finish" | "prove" | "verify";
  title: string;
  detail: string;
  state: "done" | "current" | "todo";
  links: { label: string; url: string }[];
};

export type LearningPath = {
  skill_id: number;
  skill_name: string;
  next_step: string | null;
  steps: PathStep[];
};

// Matches backend InterviewPrepResponse.
export type InterviewPrepStatus =
  | "verified"
  | "partial"
  | "provisional"
  | "not_verified"
  | "no_claim"
  | "unmapped";

export type InterviewPrepItem = {
  requirement_id: number;
  requirement_text: string;
  is_required: boolean;
  skill_id: number | null;
  skill_name: string | null;
  status: InterviewPrepStatus;
  guidance: string;
  cv_warning: string | null;
  evidence: { id: number; title: string; url: string | null; source: string | null }[];
  study_links: { mode: LearningMode; query: string; url: string }[];
};

export type InterviewPrep = {
  job_description_id: number;
  title: string | null;
  company: string | null;
  items: InterviewPrepItem[];
};

// Matches backend ExtractorInfo: which requirement reader is active, whether using it
// costs money, and the local Ollama model when that reader is on.
export type ExtractorInfo = {
  name: "skill_list" | "claude" | "ollama";
  paid: boolean;
  model: string | null;
};

export type ExtractionResponse = {
  accepted: JobRequirement[];
  rejected: { text: string; reason: string }[];
  // Existing skill-less requirements that now match a skill you've saved since.
  linked: JobRequirement[];
  // Set when the AI reader was configured but couldn't be used this time.
  note: string | null;
};

export type ComparisonResult = {
  id: number;
  job_requirement_id: number;
  knowledge_status: string;
  reasoning: string;
  evidence_ids: number[];
  created_at: string;
};

// Matches backend GapResponse.
export type Gap = {
  requirement: JobRequirement;
  result: ComparisonResult;
};

// Matches backend UserSkillResponse.
export type UserSkill = {
  id: number;
  skill_id: number;
  skill_name: string;
  status: string;
  notes: string | null;
  evidence_ids: number[];
  created_at: string;
  updated_at: string;
};

// Matches backend LearningResourceResponse / LearningModeResources /
// SkillLearningResourcesResponse.
export type LearningMode = "theory_interview" | "technical_practical";

export type LearningResource = {
  id: number;
  skill_id: number;
  mode: LearningMode;
  title: string;
  url: string;
  created_at: string;
};

export type LearningModeResources = {
  mode: LearningMode;
  search_query: string;
  search_url: string;
  resources: LearningResource[];
};

export type SkillLearningResources = {
  skill_id: number;
  skill_name: string;
  modes: LearningModeResources[];
};

// Matches backend LearningProgressResponse. "not_started" is never stored by the
// backend; it's what a skill with no progress row reports.
export type LearningProgressStatus = "not_started" | "studying" | "finished";

export type LearningProgress = {
  skill_id: number;
  skill_name: string;
  status: LearningProgressStatus;
  updated_at: string | null;
};

// Matches backend CVScanResponse / CVPresenceResponse.
export type CVSkillRef = { skill_id: number; skill_name: string };

export type CVFoundSkill = CVSkillRef & { matched_text: string; on_cv: boolean };

// Matches backend ProfileDraftsResponse: what "Fill from my CV" read (nothing saved yet).
type DraftCommon = {
  start_date: string | null;
  end_date: string | null;
  dates_text: string | null;
  description: string | null;
  duplicate: boolean;
};
export type ProfileDrafts = {
  characters: number;
  sections_found: string[];
  work_experiences: (DraftCommon & { company: string | null; role: string | null })[];
  educations: (DraftCommon & {
    institution: string | null;
    degree: string | null;
    field_of_study: string | null;
  })[];
  projects: (DraftCommon & { name: string | null; url: string | null })[];
};

// Matches backend MatchItemResponse / JobMatchResponse (match_service): always current.
export type MatchItem = { skill_id: number | null; name: string; is_required: boolean };
export type JobMatch = {
  percent: number;
  total: number;
  proven: MatchItem[];
  on_cv: MatchItem[];
  missing: MatchItem[];
  has_cv: boolean; // false: no CV skills or claims yet, so ask for the CV first
};

// Matches backend CVAdoptResponse ("Add all my CV skills"). Claims are provisional.
export type CVAdoptResult = {
  added_skills: string[];
  marked_on_cv: string[];
  claimed: string[];
  already_done: string[];
};

// Matches backend SkillSuggestionResponse: a common skill the text mentions that
// isn't saved yet (only ever a suggestion).
export type SkillSuggestion = { name: string; category: string; matched_text: string };

export type CVScan = {
  characters: number;
  found: CVFoundSkill[];
  on_cv_not_found: CVSkillRef[];
  suggestions: SkillSuggestion[];
};

export type CVPresence = {
  skill_id: number;
  skill_name: string;
  present: boolean;
  updated_at: string;
};

// Matches backend EvidenceResponse. At most one of the three source ids is set.
export type Evidence = {
  id: number;
  evidence_type: string;
  title: string;
  description: string | null;
  url: string | null;
  work_experience_id: number | null;
  project_id: number | null;
  education_id: number | null;
  created_at: string;
};

// Matches backend ProjectResponse / WorkExperienceResponse / EducationResponse.
// Dates are "YYYY-MM-DD" strings.
export type Project = {
  id: number;
  name: string;
  role: string | null;
  description: string | null;
  url: string | null;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
};

export type WorkExperience = {
  id: number;
  company: string;
  role: string;
  start_date: string;
  end_date: string | null;
  description: string | null;
  created_at: string;
};

export type Education = {
  id: number;
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  created_at: string;
};

// Matches backend AskResponse (POST /assistant/ask): RAG over your own data.
export type AssistantSource = {
  number: number; // [1], [2]... as cited
  kind: string; // overview | skill | job | gap | evidence | project | work | education
  title: string;
  text: string;
  link: string;
  score: number;
};
export type AssistantAnswer = {
  answer: string;
  sources: AssistantSource[];
  searched: number;
  retrieval: "bm25" | "vector" | "hybrid"; // keyword, meaning, or both (fused)
  note: string | null; // e.g. why meaning search or the AI writer wasn't used
  written_by: "ai" | "notes"; // an AI wrote it from the notes, or it IS the notes
};
