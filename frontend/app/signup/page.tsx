"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { apiPost, ApiError } from "@/lib/api";
import { MIN_PASSWORD, emailProblem, passwordProblem } from "@/lib/auth";
import type { User } from "@/lib/types";
import { Button } from "@/components/ui";
import { AuthCard, AuthField, FormError, PasswordField, authLinkClasses } from "@/components/AuthCard";

export default function SignupPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found = { email: emailProblem(email), password: passwordProblem(password) };
    setErrors(found);
    setProblem(null);
    if (found.email || found.password) return;
    setBusy(true);
    try {
      await apiPost<User>("/auth/signup", { email: email.trim(), password, full_name: name.trim() || null });
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- a full load on purpose: header, chat and caches must start fresh as the new user
      window.location.assign("/cv"); // first step for a new account: add your CV
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "Could not reach the server. Please try again.");
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Track the skills you can prove, match yourself to jobs, and see what to learn next."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className={authLinkClasses}>
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <FormError message={problem} />
        <AuthField
          label="Your name"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          hint="Optional. It's read from your CV later if you leave it empty."
          autoFocus
        />
        <AuthField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={errors.email}
        />
        <PasswordField
          label="Password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={errors.password}
          hint={`At least ${MIN_PASSWORD} characters.`}
        />
        <Button type="submit" variant="primary" className="mt-1 w-full py-2" disabled={busy}>
          {busy ? "Creating your account…" : "Create account"}
        </Button>
      </form>
    </AuthCard>
  );
}
