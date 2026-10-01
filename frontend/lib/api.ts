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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    // The backend's DomainError handler returns {"detail": "<message>"} as a plain
    // string (see backend/app/api/errors.py) — surface that exact message when
    // present, rather than a generic one, so e.g. a 409 duplicate-name error shows
    // the real reason instead of just "409".
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
        ? (body as { detail: string }).detail
        : `${path} responded with ${response.status}`;
    throw new ApiError(detail, response.status);
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
