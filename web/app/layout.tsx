import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SEC Filing Terminal",
  description: "10-K statements, traceable ratios and DEF 14A governance checks for any public company.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;1,8..60,400&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
