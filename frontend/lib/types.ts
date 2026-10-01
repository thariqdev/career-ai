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

export type JobDescription = {
  id: number;
  title: string | null;
  company: string | null;
  source_url: string | null;
  raw_text: string;
  created_at: string;
  requirements: JobRequirement[];
};

export type ExtractionResponse = {
  accepted: JobRequirement[];
  rejected: { text: string; reason: string }[];
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

export type CVScan = {
  characters: number;
  found: CVFoundSkill[];
  on_cv_not_found: CVSkillRef[];
};

export type CVPresence = {
  skill_id: number;
  skill_name: string;
  present: boolean;
  updated_at: string;
};

// Matches backend EvidenceResponse.
export type Evidence = {
  id: number;
  evidence_type: string;
  title: string;
  description: string | null;
  url: string | null;
  created_at: string;
};
