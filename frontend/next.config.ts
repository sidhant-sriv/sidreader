import type { NextConfig } from "next";

const API_ORIGIN = process.env.SIDREADER_API ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [
      { source: "/documents/:path*", destination: `${API_ORIGIN}/documents/:path*` },
      { source: "/parse/:path*", destination: `${API_ORIGIN}/parse/:path*` },
    ];
  },
};

export default nextConfig;
