/**
 * Small shared building blocks, so every page looks the same without repeating long
 * class lists. Looks only: no data fetching or behavior lives here. Colors and fonts
 * come from the tokens in app/globals.css (bg-surface, text-ink, border-line, …).
 */

import Link from "next/link";
import type { ButtonHTMLAttributes, ComponentPropsWithRef, ReactNode } from "react";

type Variant = "primary" | "plain" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-accent text-surface hover:opacity-90",
  plain: "border border-line bg-surface text-ink hover:bg-ground",
  danger: "border border-not-verified bg-surface text-not-verified hover:bg-not-verified-bg",
};

type Size = "sm" | "md";

const BASE_BUTTON =
  "inline-flex items-center justify-center gap-1 rounded-md font-medium " +
  "transition-colors disabled:cursor-not-allowed disabled:opacity-50";

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-3 py-1.5 text-sm",
};

export function buttonClasses(variant: Variant = "plain", extra = "", size: Size = "md"): string {
  return `${BASE_BUTTON} ${SIZE_CLASSES[size]} ${VARIANT_CLASSES[variant]} ${extra}`.trim();
}

export function Button({
  variant = "plain",
  size = "md",
  className = "",
  type = "button",
  ...props
}: ComponentPropsWithRef<"button"> & { variant?: Variant; size?: Size }) {
  return <button type={type} className={buttonClasses(variant, className, size)} {...props} />;
}

/** One option in a row of choices (status, progress): filled when selected. */
export function Pill({
  selected,
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { selected: boolean }) {
  return (
    <button
      type={type}
      aria-pressed={selected}
      className={`rounded-full border px-3 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        selected
          ? "border-accent bg-accent text-surface"
          : "border-line bg-surface text-ink-soft hover:border-accent hover:text-ink"
      } ${className}`.trim()}
      {...props}
    />
  );
}

/** The standard text input / select / textarea look. */
export const inputClasses =
  "rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink " +
  "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent-soft";

/** The red look for a box with a problem; add it to inputClasses. */
export const invalidClasses = "border-not-verified focus:border-not-verified focus:ring-not-verified-bg";

/** A box's own problem, shown right under it (instead of the browser's pop-up bubble). */
export function FieldError({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <span role="alert" className="text-xs font-medium text-not-verified">
      {message}
    </span>
  );
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
