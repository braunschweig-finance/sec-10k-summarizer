import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SEC Financial & Corporate Governance Terminal",
  description: "10-K statements, ratios traced to the filed line item, and DEF 14A governance checks for any public company.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Besley:ital,wght@0,400;0,600;0,800;1,400&family=IBM+Plex+Mono:wght@400&family=Public+Sans:wght@400;500;600&display=swap"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
