import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { SESSION_COOKIE, isAuthPage, loginUrl } from "@/lib/auth";

/**
 * The front door (stage 99; Next.js 16 calls middleware "proxy"). An optimistic check
 * only: no login cookie -> the login page; a login cookie on an account page -> the
 * app. The backend still checks every request itself, so a stale or forged cookie gets
 * a 401 and the API client sends the person to /login.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const loggedIn = request.cookies.has(SESSION_COOKIE);

  if (!loggedIn && !isAuthPage(pathname)) {
    return NextResponse.redirect(new URL(loginUrl(pathname + search), request.url));
  }
  if (loggedIn && (pathname === "/login" || pathname === "/signup")) {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Every page, but not the API forwarding, Next.js's own files or static files.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.[a-zA-Z0-9]+$).*)"],
};
