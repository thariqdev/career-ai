"use client";

import Link from "next/link";
import { useId, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { FieldError, inputClasses, invalidClasses } from "@/components/ui";

/**
 * The frame every account page shares (stage 99): the Career AI name, a heading and a
 * short line under it, then the form in a card, with links underneath. Same fonts,
 * colors and form styles as the rest of the app, without the main menu.
 */
export function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="flex flex-1 items-start justify-center px-4 py-12 sm:py-20">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 block text-center font-display text-2xl text-ink">
          Career <span className="text-accent">AI</span>
        </Link>
        <div className="rounded-lg border border-line bg-surface p-6 shadow-sm sm:p-7">
          <h1 className="font-display text-2xl text-ink">{title}</h1>
          {subtitle && <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        {footer && <div className="mt-5 text-center text-sm text-ink-soft">{footer}</div>}
      </div>
    </main>
  );
}

// Autofill / password-manager extensions stamp attributes (e.g. fdprocessedid) onto form
// controls before React hydrates; that harmless mismatch is ignored on these elements only.

/** A labelled input with its own problem shown under it. */
export function AuthField({
  label,
  error,
  hint,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string | null; hint?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={id}
        suppressHydrationWarning
        aria-invalid={Boolean(error)}
        className={`${inputClasses} py-2 ${error ? invalidClasses : ""}`}
        {...input}
      />
      {error ? <FieldError message={error} /> : hint && <span className="text-xs text-ink-soft">{hint}</span>}
    </div>
  );
}

/** A password box with a Show / Hide switch, so people can check what they typed. */
export function PasswordField({
  label,
  error,
  hint,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string | null; hint?: string }) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          suppressHydrationWarning
          type={visible ? "text" : "password"}
          aria-invalid={Boolean(error)}
          className={`${inputClasses} w-full py-2 pr-16 ${error ? invalidClasses : ""}`}
          {...input}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          suppressHydrationWarning
          aria-label={visible ? "Hide password" : "Show password"}
          className="absolute inset-y-0 right-0 rounded-r-md px-3 text-xs font-medium text-ink-soft hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-soft"
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
      {error ? <FieldError message={error} /> : hint && <span className="text-xs text-ink-soft">{hint}</span>}
    </div>
  );
}

/** A problem with the whole form (e.g. "Wrong email or password."). */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md bg-not-verified-bg px-3 py-2 text-sm text-not-verified">
      {message}
    </p>
  );
}

/** A friendly confirmation (e.g. "Check your inbox"). */
export function FormNotice({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-verified-bg px-3 py-2 text-sm text-verified">{children}</p>;
}

export const authLinkClasses = "font-medium text-accent underline-offset-2 hover:underline";
