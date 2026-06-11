/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  allowedDevOrigins: ['165.245.174.63'],

  async redirects() {
    return [
      {
        source: '/termsofservice',
        destination: '/terms',
        permanent: true,
      },
      {
        source: '/tos',
        destination: '/terms',
        permanent: true,
      },
      {
        source: '/privacypolicy',
        destination: '/privacy',
        permanent: true,
      },
      {
        source: '/pp',
        destination: '/privacy',
        permanent: true,
      }
    ]
  },
}

export default nextConfig