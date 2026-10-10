/**
 * A small, typed fetch helper for talking to the Career AI backend.
 *
 * The base URL comes from NEXT_PUBLIC_API_BASE_URL (see .env.local.example). The
 * NEXT_PUBLIC_ prefix is required by Next.js for any environment variable that
 * needs to be readable in browser-side code, not just on the server — without
 * it, the value would only exist during the server build and be undefined here.
 *
 * This is deliberately minimal: six functions sharing one internal helper, no
 * retries, no caching, no request library. They just call `fetch`, check the
 * status, and parse JSON.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
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
  });
  if (!response.ok || response.body === null) {
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
