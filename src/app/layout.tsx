import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Buoyancy Labs Inc.",
  description:
    "Voice AI for Indian businesses — RA-1 & G-1. Intelligent, emotional, deeply local customer support.",
};

const themeScript = `
try {
  var mode = localStorage.getItem("buoyancy-theme") || "system";
  if (mode !== "system" && mode !== "light" && mode !== "dark") mode = "system";
  var resolved = mode === "system"
    ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
    : mode;
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
} catch (_) {}
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
      data-scroll-behavior="smooth"
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body
        className="min-h-full flex flex-col bg-white text-neutral-900"
        style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif' }}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
