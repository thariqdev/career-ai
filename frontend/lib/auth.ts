/**
 * Small rules for the account pages (stage 99), kept pure so they can be tested.
 * Used by proxy.ts (the redirect to /login), the API client (on a 401) and the pages.
 */

export const SESSION_COOKIE = "career_ai_session";
export const MIN_PASSWORD = 8;
export const MAX_PASSWORD = 128;

/** Pages anyone can open without logging in. */
export const AUTH_PAGES = ["/login", "/signup", "/forgot-password", "/reset-password"];

export function isAuthPage(pathname: string): boolean {
  return AUTH_PAGES.some((page) => pathname === page || pathname.startsWith(`${page}/`));
}

/**
 * Where to go after logging in. Only a page of this site: a relative path that isn't
 * protocol-relative ("//evil.com") and isn't an account page. Anything else -> "/".
 */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/";
  const pathname = next.split(/[?#]/)[0];
  return isAuthPage(pathname) ? "/" : next;
}

/** The login page, remembering where the person was going. */
export function loginUrl(currentPath: string): string {
  const next = safeNext(currentPath);
  return next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`;
}

/** A readable problem with a new password, or null when it's fine. */
export function passwordProblem(password: string): string | null {
  if (password.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (password.length > MAX_PASSWORD) return `Use at most ${MAX_PASSWORD} characters.`;
  return null;
}

/** A readable problem with an email address, or null when it looks fine. */
export function emailProblem(email: string): string | null {
  const clean = email.trim();
  if (!clean) return "Email is required.";
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(clean) ? null : "Please enter a valid email address.";
}
