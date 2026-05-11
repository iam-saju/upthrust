import type { ReactNode } from "react";

export function LabSection({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="mb-10 sm:mb-14 md:mb-20 scroll-mt-8 last:mb-0">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,0.28fr)_minmax(0,0.72fr)] gap-x-10 md:gap-x-14 lg:gap-x-24 gap-y-4 items-start">
        <p className="text-[13px] md:text-[15px] text-neutral-500 md:pt-[0.3em] tracking-[0.02em]" style={{ fontFamily: 'var(--font-inter), -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif' }}>
          {label}
        </p>
        <div className="min-w-0 space-y-6 text-[17px] md:text-lg leading-[1.65] text-neutral-900" style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif' }}>
          {children}
        </div>
      </div>
    </section>
  );
}
