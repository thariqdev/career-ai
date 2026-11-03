"use client";

import Link from "next/link";
import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { apiPost, ApiError } from "@/lib/api";
import { MIN_PASSWORD, passwordProblem } from "@/lib/auth";
import type { User } from "@/lib/types";
import { Button, ButtonLink } from "@/components/ui";
import { AuthCard, FormError, PasswordField, authLinkClasses } from "@/components/AuthCard";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ password?: string | null; confirm?: string | null }>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = {
      password: passwordProblem(password),
      confirm: confirm === password ? null : "The two passwords don't match.",
    };
    setErrors(found);
    setProblem(null);
    if (found.password || found.confirm) return;
    setBusy(true);
    try {
      await apiPost<User>("/auth/reset-password", { token, new_password: password });
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- a full load on purpose: header, chat and caches must start fresh as the new user
      window.location.assign("/"); // logged in with the new password
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "Could not reach the server. Please try again.");
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <AuthCard title="This link isn't complete" subtitle="Open the link from your email again, or ask for a new one.">
        <ButtonLink href="/forgot-password" variant="primary" className="w-full py-2">
          Ask for a new link
        </ButtonLink>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Choose a new password"
      subtitle="You'll be logged out everywhere else, and logged in here."
      footer={
        <Link href="/login" className={authLinkClasses}>
          Back to log in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <FormError message={problem} />
        {problem?.includes("Ask for a new one") && (
          <Link href="/forgot-password" className={`${authLinkClasses} text-sm`}>
            Send me a new link
          </Link>
        )}
        <PasswordField
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          hint={`At least ${MIN_PASSWORD} characters.`}
          autoFocus
        />
        <PasswordField
          label="Type it again"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          error={errors.confirm}
        />
        <Button type="submit" variant="primary" className="mt-1 w-full py-2" disabled={busy}>
          {busy ? "Saving…" : "Save new password"}
        </Button>
      </form>
    </AuthCard>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  );
}
