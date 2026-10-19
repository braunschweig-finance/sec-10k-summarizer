/** @type {import('next').NextConfig} */
const nextConfig = {
  // The site is plain static files; all SEC work happens in the Python API (../api)
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
