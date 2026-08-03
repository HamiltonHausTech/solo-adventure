import type { Metadata } from "next";
import { Cormorant_Garamond, Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const serif = Cormorant_Garamond({ variable: "--font-serif", subsets: ["latin"], weight: ["500", "600", "700"] });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Solo Adventure — The Ruined Watchtower",
  description: "A browser-playable solo fantasy campaign with deterministic rules, companions, combat, sound, and local saves.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: {
    title: "Solo Adventure — The Ruined Watchtower",
    description: "Enter the tower. Trust the dice. Survive the watch.",
    type: "website",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Solo Adventure: The Ruined Watchtower" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Solo Adventure — The Ruined Watchtower",
    description: "Enter the tower. Trust the dice. Survive the watch.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${serif.variable} ${mono.variable}`}>{children}</body>
    </html>
  );
}
