/**
 * Small shared building blocks, so every page looks the same without repeating long
 * class lists. Looks only: no data fetching or behavior lives here. Colors and fonts
 * come from the tokens in app/globals.css (bg-surface, text-ink, border-line, …).
 */

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "plain" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-accent text-surface hover:opacity-90",
  plain: "border border-line bg-surface text-ink hover:bg-ground",
  danger: "border border-not-verified bg-surface text-not-verified hover:bg-not-verified-bg",
};

const BASE_BUTTON =
  "inline-flex items-center justify-center gap-1 rounded-md px-3 py-1.5 text-sm font-medium " +
  "transition-colors disabled:cursor-not-allowed disabled:opacity-50";

export function buttonClasses(variant: Variant = "plain", extra = ""): string {
  return `${BASE_BUTTON} ${VARIANT_CLASSES[variant]} ${extra}`.trim();
}

export function Button({
  variant = "plain",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button type={type} className={buttonClasses(variant, className)} {...props} />;
}

/** A link styled like a button (e.g. "Next step: …"). */
export function ButtonLink({
  href,
  variant = "plain",
  className = "",
  children,
}: {
  href: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={buttonClasses(variant, className)}>
      {children}
    </Link>
  );
}

/** A white box with a soft border: the basic container for one piece of content. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-line bg-surface p-5 shadow-sm ${className}`.trim()}>
      {children}
    </div>
  );
}

/** A section title with an optional one-line explanation and right-hand actions. */
export function SectionHeading({
  title,
  hint,
  actions,
}: {
  title: string;
  hint?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="font-display text-lg text-ink">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-ink-soft">{hint}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** Friendly "nothing here yet" text, ideally saying what to do first. */
export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-line px-4 py-3 text-sm text-ink-soft">
      {children}
    </p>
  );
}

/** The standard page wrapper: width, padding and the page title. */
export function Page({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6">
      {title && <h1 className="font-display text-3xl text-ink">{title}</h1>}
      {children}
    </main>
  );
}
