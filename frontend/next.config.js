/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  turbopack: {
    root: '..',
  },
  async rewrites() {
    // Proxy /api/* to backend in ALL environments so cookies are always
    // first-party (same origin).  Without this, cross-domain cookies are
    // blocked in Chrome Incognito and other strict-cookie browsers.
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
