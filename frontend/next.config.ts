import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone with only the files the server actually needs, so
  // the runtime image does not carry node_modules or the build toolchain.
  output: "standalone",

  // The command centre gets opened at both http://localhost:3000 and
  // http://127.0.0.1:3000. Without this, Next blocks its own dev resources on
  // whichever one it did not start under, and the page never hydrates.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
