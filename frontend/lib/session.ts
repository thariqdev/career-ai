import { apiPost } from "@/lib/api";

/** Log out here (stage 99): the server ends the session and clears the cookie. */
export async function logOut(): Promise<void> {
  try {
    await apiPost("/auth/logout", {});
  } finally {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- a full load on purpose: header, chat and caches must start fresh as the new user
    window.location.assign("/login"); // even if the server was unreachable
  }
}
