"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { apiPost, ApiError } from "@/lib/api";
import { emailProblem } from "@/lib/auth";
import { Button } from "@/components/ui";
import { AuthCard, AuthField, FormError, FormNotice, authLinkClasses } from "@/components/AuthCard";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = emailProblem(email);
    setError(found);
    setProblem(null);
    if (found) return;
    setBusy(true);
    try {
      // The same reply whether or not the account exists (so nobody can probe emails).
      const reply = await apiPost<{ detail: string }>("/auth/forgot-password", { email: email.trim() });
      setSent(reply.detail);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : "Could not reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a link to choose a new one."
      footer={
        <Link href="/login" className={authLinkClasses}>
          Back to log in
        </Link>
      }
    >
      {sent ? (
        <div className="flex flex-col gap-4">
          <FormNotice>{sent}</FormNotice>
          <p className="text-sm leading-relaxed text-ink-soft">
            The link works once, for 30 minutes. No email after a few minutes? Check your spam folder, or try again.
          </p>
          <Button onClick={() => setSent(null)} className="w-full py-2">
            Send another link
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
          <FormError message={problem} />
          <AuthField
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={error}
            autoFocus
          />
          <Button type="submit" variant="primary" className="mt-1 w-full py-2" disabled={busy}>
            {busy ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthCard>
  );
}
