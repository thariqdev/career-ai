"use client";

import { useEffect, useState } from "react";
import { apiGet, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

/**
 * Fetches GET /me once and returns the same three-state shape the home page's
 * proof-of-connection code already established (loading / loaded / error).
 *
 * Extracted into one small hook, reused by both AppHeader (the user chip) and
 * potentially anywhere else that needs "who am I", rather than each place
 * copy-pasting its own near-identical useEffect + fetch block.
 */
type MeState =
  | { status: "loading" }
  | { status: "loaded"; user: User }
  | { status: "error"; message: string };

export function useMe(): MeState {
  const [state, setState] = useState<MeState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    apiGet<User>("/me")
      .then((user) => {
        if (active) setState({ status: "loaded", user });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const message =
          error instanceof ApiError
            ? error.message
            : "Could not reach the backend.";
        setState({ status: "error", message });
      });
    return () => {
      active = false;
    };
  }, []);

  return state;
}
