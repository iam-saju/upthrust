import type { Metadata } from "next";
import { Inter, Instrument_Serif } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-inter",
});

const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  weight: ["400"],
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
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
        className={`${inter.variable} ${instrumentSerif.variable} min-h-full flex flex-col bg-white text-neutral-900`}
        style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif' }}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
