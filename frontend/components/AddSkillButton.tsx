"use client";

import { useState } from "react";
import Link from "next/link";
import { apiPost, ApiError } from "@/lib/api";
import { Button } from "@/components/ui";

/**
 * "Add to my skills" for a skill a job asks for that you haven't saved (stage 90).
 * POST /skills/from-catalogue: catalogue skills only, never a duplicate. It only adds the
 * skill to the list you track (learning path, progress, links, proof later): it does NOT
 * claim it or mark it on your CV, so the gap stays a gap until you prove it.
 */
export default function AddSkillButton({ name }: { name: string }) {
  const [state, setState] = useState<{ busy: boolean; skillId: number | null; error: string | null }>({
    busy: false,
    skillId: null,
    error: null,
  });

  async function add() {
    setState({ busy: true, skillId: null, error: null });
    try {
      const body = await apiPost<{ skill: { id: number }; created: boolean }>("/skills/from-catalogue", { name });
      setState({ busy: false, skillId: body.skill.id, error: null });
    } catch (err) {
      setState({ busy: false, skillId: null, error: err instanceof ApiError ? err.message : "Could not reach the backend." });
    }
  }

  if (state.skillId !== null) {
    return (
      <span className="text-xs text-verified">
        ✓ Added to your skills ·{" "}
        <Link href={`/skills/${state.skillId}`} className="underline">
          Open {name} →
        </Link>
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-2">
      <Button
        size="sm"
        onClick={add}
        disabled={state.busy}
        title="Adds it to the skills you track. It doesn't claim it or mark it on your CV."
      >
        {state.busy ? "Adding…" : "Add to my skills"}
      </Button>
      {state.error && (
        <span role="alert" className="text-xs text-not-verified">
          {state.error}
        </span>
      )}
    </span>
  );
}
