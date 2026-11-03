/**
 * A small, typed fetch helper for talking to the Career AI backend.
 *
 * Every call goes to this site's own /api/..., which Next.js forwards to the backend
 * (next.config.ts, stage 99). Same site = the login cookie is sent automatically and
 * browsers accept it. A 401 ("Please log in") anywhere except the login routes
 * themselves sends the person to /login, remembering the page they were on.
 *
 * This is deliberately minimal: a few functions sharing one internal helper, no
 * retries, no caching, no request library. They just call `fetch`, check the
 * status, and parse JSON.
 */

import { isAuthPage, loginUrl } from "@/lib/auth";

const API_BASE_URL = "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// "start_date" -> "Start date"
function fieldLabel(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * A message a person can read, never a status code or a URL. The backend's own rules
 * send {"detail": "<sentence>"}; FastAPI's input checks send a list of problems
 * ({loc, msg}), which becomes e.g. "Institution is required."
 */
function errorText(body: unknown, status: number): string {
  const detail = body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((problem: { loc?: unknown[]; msg?: string; type?: string; input?: unknown }) => {
        const key = String(problem.loc?.[problem.loc.length - 1] ?? "This field");
        // Missing, or sent empty (null) where text or a date is needed.
        if (problem.type === "missing" || problem.input === null) {
          return `${fieldLabel(key)} is required.`;
        }
        return `${fieldLabel(key)}: ${problem.msg ?? "isn't valid"}.`;
      })
      .join(" ");
  }
  return status >= 500
    ? "Something went wrong on the server. Please try again."
    : "That couldn't be saved. Please check the details and try again.";
}

// Logged out (or the session expired): go to the login page, then come back here.
function goToLogin(path: string, status: number): void {
  if (status !== 401 || path.startsWith("/auth/") || typeof window === "undefined") return;
  if (isAuthPage(window.location.pathname)) return;
  window.location.assign(loginUrl(window.location.pathname + window.location.search));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "same-origin", ...init });
  if (!response.ok) {
    goToLogin(path, response.status);
    // The backend's DomainError handler returns {"detail": "<message>"} as a plain
    // string (see backend/app/api/errors.py) — surface that exact message when
    // present, rather than a generic one, so e.g. a 409 duplicate-name error shows
    // the real reason instead of just "409".
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(errorText(body, response.status), response.status);
  }
  // 204 No Content (e.g. a DELETE) has no body to parse.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// For file uploads. No Content-Type header on purpose: the browser sets the
// multipart boundary itself, and setting it by hand would break the upload.
export function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: form });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// T defaults to void for 204 No Content; pass a type when the endpoint returns a body.
export function apiDelete<T = void>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * POST and read a streamed NDJSON response line by line, calling onEvent for each object
 * as it arrives (the assistant's answer appearing word by word). `signal` lets the caller
 * stop it (an AbortController for a "Stop" button). Errors before the stream starts
 * (e.g. 422) throw ApiError with a readable message, like the other helpers.
 */
export async function apiStream<E>(
  path: string,
  body: unknown,
  onEvent: (event: E) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
    credentials: "same-origin",
  });
  if (!response.ok || response.body === null) {
    goToLogin(path, response.status);
    const errorBody: unknown = await response.json().catch(() => null);
    throw new ApiError(errorText(errorBody, response.status), response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    // A chunk can end halfway through a line: handle whole lines, keep the rest.
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) if (line.trim() !== "") onEvent(JSON.parse(line) as E);
    if (done) break;
  }
  if (buffer.trim() !== "") onEvent(JSON.parse(buffer) as E);
}
