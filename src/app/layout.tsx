import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-inter",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-space-grotesk",
});

export const metadata: Metadata = {
  title: "Buoyancy Labs Inc.",
  description:
    "Voice AI for Indian businesses — RA-1 & G-1. Intelligent, emotional, deeply local customer support.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${spaceGrotesk.variable} min-h-full flex flex-col font-serif bg-white text-neutral-900`}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
