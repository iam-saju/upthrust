import type { Metadata } from "next";
import "./globals.css";

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
        className="min-h-full flex flex-col font-serif bg-white text-neutral-900"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
