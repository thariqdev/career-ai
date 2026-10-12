"use client";

import { useState } from "react";
import { apiGet, ApiError } from "@/lib/api";
import { Button, Card, SectionHeading } from "@/components/ui";

// Fetches GET /export and saves it as a file in the browser. Read-only: the backend
// never changes anything when exporting. Also the backup taken before "Start fresh".
export async function downloadExport(): Promise<void> {
  const data = await apiGet<unknown>("/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `career-ai-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function DownloadMyData() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleClick() {
    setError(null);
    setDone(false);
    setBusy(true);
    try {
      await downloadExport();
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the backend.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeading
        title="Download my data"
        hint="One file with everything Career AI stores for you: skills and nicknames, claims, evidence, this profile, job postings and their results, CV marks, learning progress and saved links. Keep it as a backup."
        actions={
          <Button variant="primary" onClick={handleClick} disabled={busy}>
            {busy ? "Preparing…" : "Download (.json)"}
          </Button>
        }
      />
      {done && <p className="mt-3 text-sm text-verified">✓ Saved to your downloads.</p>}
      {error && <p className="mt-3 text-sm text-not-verified">{error}</p>}
    </Card>
  );
}
