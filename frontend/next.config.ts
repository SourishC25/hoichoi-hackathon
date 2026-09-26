import type { NextConfig } from "next";

// Built as a static SPA (out/) and served by the FastAPI backend — one service, one URL.
// The same build also powers the free static mirror (with runtime.json → {"static": true}).
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
