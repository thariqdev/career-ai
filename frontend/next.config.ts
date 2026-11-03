import type { NextConfig } from "next";

// The backend's address, read by the server only (stage 99). The browser always calls
// this site's own /api/..., and Next.js forwards it here, so the login cookie belongs to
// this site and browsers accept it (a cookie from another site would be blocked).
const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactCompiler: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
};

export default nextConfig;
