"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { CVStatus, CVStatusResponse } from "@/lib/types";

// No design token was given for the three cv_status values, so these are a small
// choice of our own: accent (teal) for a skill actually on the CV, warm (amber) for
// "missing from the CV" since that's the actionable one, neutral for "not present".
export function cvBadgeClasses(status: CVStatus): string {
  switch (status) {
    case "present":
      return "bg-accent-soft text-accent";
    case "missing_from_cv":
      return "bg-warm-soft text-warm";
    case "not_present":
      return "bg-line text-ink-soft";
  }
}

export function cvBadgeLabel(status: CVStatus): string {
  return status.replace(/_/g, " ");
}

/**
 * GET /cv/status once, keyed by skill id. A skill missing from the result has no
 * claim and no CV mark, so callers treat it as "not_present". A failed request
 * just yields an empty map, so a page shows no CV info instead of failing.
 */
export function useCvStatuses(): Record<number, CVStatusResponse> {
  const [byId, setById] = useState<Record<number, CVStatusResponse>>({});

  useEffect(() => {
    let active = true;
    apiGet<CVStatusResponse[]>("/cv/status")
      .then((list) => {
        if (!active) return;
        const next: Record<number, CVStatusResponse> = {};
        for (const entry of list) next[entry.skill_id] = entry;
        setById(next);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  return byId;
}
