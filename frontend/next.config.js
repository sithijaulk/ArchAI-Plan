/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",  // Required for Docker multi-stage build
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**",
      },
      {
        protocol: "http",
        hostname: "localhost",
      },
    ],
  },
};

export default nextConfig;
