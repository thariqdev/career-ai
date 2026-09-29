import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import AppHeader from "@/components/AppHeader";
import "./globals.css";

// next/font/google, not a manual <link> tag: Next.js downloads and self-hosts the
// font at build time and exposes it as a CSS variable, which globals.css then maps
// to a Tailwind utility (font-display/font-sans/font-mono). Fraunces = headings,
// IBM Plex Sans = body text, IBM Plex Mono = status badges and small data labels.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
});

const ibmPlexSans = IBM_Plex_Sans({
  variable: "--font-ibm-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Career AI",
  description: "A personal career and technical-knowledge system.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${ibmPlexSans.variable} ${ibmPlexMono.variable} h-full antialiased`}
      // Browser extensions sometimes stamp their own attributes onto <html> before
      // React hydrates, which looks like a mismatch but isn't a real bug (see the
      // "Frontend skeleton" section of HANDOFF.md). This only quiets warnings about
      // this one tag; it does not hide real mismatches anywhere else in the page.
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col bg-ground text-ink">
        <AppHeader />
        {children}
      </body>
    </html>
  );
}
