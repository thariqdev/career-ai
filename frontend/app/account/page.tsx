"use client";

import { useState, type FormEvent } from "react";
import { apiPost, ApiError } from "@/lib/api";
import { MIN_PASSWORD, passwordProblem } from "@/lib/auth";
import { logOut } from "@/lib/session";
import { useMe } from "@/lib/useMe";
import type { User } from "@/lib/types";
import { Button, Card, Page, SectionHeading } from "@/components/ui";
import { FormError, FormNotice, PasswordField } from "@/components/AuthCard";

function ChangePassword() {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ current?: string | null; password?: string | null; confirm?: string | null }>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = {
      current: current ? null : "Enter your current password.",
      password: passwordProblem(password),
      confirm: confirm === password ? null : "The two passwords don't match.",
    };
    setErrors(found);
    setProblem(null);
    setDone(false);
    if (found.current || found.password || found.confirm) return;
    setBusy(true);
    try {
      await apiPost<User>("/auth/change-password", { current_password: current, new_password: password });
      setCurrent("");
      setPassword("");
      setConfirm("");
      setDone(true);
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionHeading title="Change password" hint="Other devices are logged out; this one stays logged in." />
      <form onSubmit={handleSubmit} noValidate className="mt-4 flex max-w-sm flex-col gap-4">
        <FormError message={problem} />
        {done && <FormNotice>✓ Password changed.</FormNotice>}
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          error={errors.current}
        />
        <PasswordField
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          hint={`At least ${MIN_PASSWORD} characters.`}
        />
        <PasswordField
          label="Type it again"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
        />
        <Button type="submit" variant="primary" className="self-start" disabled={busy}>
          {busy ? "Saving…" : "Save new password"}
        </Button>
      </form>
    </Card>
  );
}

export default function AccountPage() {
  const me = useMe();
  return (
    <Page title="Account">
      <p className="mt-1 text-sm text-ink-soft">Your login details. Everything you add in Career AI is private to this account.</p>
      <div className="mt-6 flex flex-col gap-6">
        <Card>
          <SectionHeading title="Logged in as" />
          <p className="mt-3 text-sm text-ink">
            {me.status === "loaded" ? (
              <>
                {me.user.full_name && <span className="font-medium">{me.user.full_name} · </span>}
                <span className="font-mono text-ink-soft">{me.user.email}</span>
              </>
            ) : (
              <span className="text-ink-soft">…</span>
            )}
          </p>
          <Button onClick={logOut} className="mt-4">
            Log out
          </Button>
        </Card>
        <ChangePassword />
      </div>
    </Page>
  );
}
