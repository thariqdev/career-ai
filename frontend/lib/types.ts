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
