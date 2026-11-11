import type { NextConfig } from "next";

// Kavra is a client-heavy study app talking to a local FastAPI backend, so it keeps the
// classic rendering model (no Cache Components / partial prefetching).
const nextConfig: NextConfig = {
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
