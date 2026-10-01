"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { LearningMode, SkillLearningResources } from "@/lib/types";

export const MODE_LABEL: Record<LearningMode, string> = {
  theory_interview: "Theory / Interview",
  technical_practical: "Technical / Practical",
};

/**
 * Fetches GET /skills/{id}/learning-resources once per distinct skill id and
 * returns them keyed by skill id. One request per skill (the same accepted
 * per-item pattern as elsewhere) keeps the search-query wording in the backend
 * only. A skill whose request fails is simply missing from the result, so a
 * caller hides that skill's buttons instead of failing the whole page.
 */
export function useLearningResources(skillIds: number[]): Record<number, SkillLearningResources> {
  const key = [...new Set(skillIds)].sort((a, b) => a - b).join(",");
  const [byId, setById] = useState<Record<number, SkillLearningResources>>({});

  useEffect(() => {
    let active = true;
    const ids = key === "" ? [] : key.split(",").map(Number);
    Promise.all(
      ids.map((id) =>
        apiGet<SkillLearningResources>(`/skills/${id}/learning-resources`).catch(() => null),
      ),
    ).then((results) => {
      if (!active) return;
      const next: Record<number, SkillLearningResources> = {};
      for (const result of results) {
        if (result) next[result.skill_id] = result;
      }
      setById(next);
    });
    return () => {
      active = false;
    };
  }, [key]);

  return byId;
}
