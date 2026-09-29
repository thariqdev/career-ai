"use client";

import { useEffect, useState } from "react";
import { apiGet, ApiError } from "@/lib/api";

// Shapes match backend/app/core/models.py's HealthResponse and UserResponse.
type HealthResponse = { status: string };
type UserResponse = { id: number; email: string; full_name: string | null };

// This is a proof-of-connection page only: it calls the backend and shows what
// comes back, nothing more. No styling/design pass — that is a separate later task.
type State =
  | { status: "loading" }
  | { status: "loaded"; health: HealthResponse; me: UserResponse }
  | { status: "error"; message: string };

export default function Home() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    async function load() {
      try {
        const [health, me] = await Promise.all([
          apiGet<HealthResponse>("/health"),
          apiGet<UserResponse>("/me"),
        ]);
        setState({ status: "loaded", health, me });
      } catch (error) {
        const message =
          error instanceof ApiError
            ? error.message
            : "Could not reach the backend. Is it running?";
        setState({ status: "error", message });
      }
    }
    load();
  }, []);

  return (
    <main className="p-6 font-mono text-sm text-ink">
      <h1 className="font-display text-lg">Career AI — backend connection check</h1>

      {state.status === "loading" && <p className="text-ink-soft">Loading…</p>}

      {state.status === "error" && (
        <p className="text-not-verified">Error: {state.message}</p>
      )}

      {state.status === "loaded" && (
        <div>
          <p>GET /health → {JSON.stringify(state.health)}</p>
          <p>GET /me → {JSON.stringify(state.me)}</p>
        </div>
      )}
    </main>
  );
}
