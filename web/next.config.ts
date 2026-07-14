import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Standalone output: the Docker image copies only .next/standalone (not the
  // full node_modules) → lighter build. See web/Dockerfile.
  output: 'standalone',
};

export default nextConfig;
