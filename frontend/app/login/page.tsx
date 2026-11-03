"use client";

import Link from "next/link";
import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { apiPost, ApiError } from "@/lib/api";
import { emailProblem, safeNext } from "@/lib/auth";
import type { User } from "@/lib/types";
import { Button } from "@/components/ui";
import { AuthCard, AuthField, FormError, PasswordField, authLinkClasses } from "@/components/AuthCard";

function LoginForm() {
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = { email: emailProblem(email), password: password ? null : "Password is required." };
    setErrors(found);
    setProblem(null);
    if (found.email || found.password) return;
    setBusy(true);
    try {
      await apiPost<User>("/auth/login", { email: email.trim(), password });
      window.location.assign(next); // a full load on purpose: header, chat and caches start fresh as you
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "Could not reach the server. Please try again.");
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Log in"
      subtitle="Welcome back. Your skills, jobs and progress are waiting."
      footer={
        <>
          New to Career AI?{" "}
          <Link href="/signup" className={authLinkClasses}>
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {problem === "Wrong email or password." ? (
          // Still never says whether the email has an account (that would let anyone probe
          // emails), but points new people to sign-up.
          <p role="alert" className="rounded-md bg-not-verified-bg px-3 py-2 text-sm text-not-verified">
            Wrong email or password. New here?{" "}
            <Link href="/signup" className="font-medium underline underline-offset-2">
              Create an account
            </Link>
          </p>
        ) : (
          <FormError message={problem} />
        )}
        <AuthField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
          autoFocus
        />
        <div className="flex flex-col gap-1.5">
          <PasswordField
            label="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={errors.password}
          />
          <Link href="/forgot-password" className={`${authLinkClasses} self-end text-xs`}>
            Forgot password?
          </Link>
        </div>
        <Button type="submit" variant="primary" className="mt-1 w-full py-2" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </Button>
      </form>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
