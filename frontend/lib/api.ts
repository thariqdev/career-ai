/**
 * A small, typed fetch helper for talking to the Career AI backend.
 *
 * The base URL comes from NEXT_PUBLIC_API_BASE_URL (see .env.local.example). The
 * NEXT_PUBLIC_ prefix is required by Next.js for any environment variable that
 * needs to be readable in browser-side code, not just on the server — without
 * it, the value would only exist during the server build and be undefined here.
 *
 * This is deliberately minimal: one function, no retries, no caching, no request
 * library. It just calls `fetch`, checks the status, and parses JSON.
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

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new ApiError(
      `${path} responded with ${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}
