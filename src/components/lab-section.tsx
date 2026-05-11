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
    <section id={id} className="mb-20 md:mb-40 scroll-mt-8 last:mb-0">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,0.28fr)_minmax(0,0.72fr)] gap-x-10 md:gap-x-14 lg:gap-x-24 gap-y-4 items-start">
        <p className="text-[13px] md:text-[15px] text-neutral-500 md:pt-[0.3em] tracking-[0.02em]">
          {label}
        </p>
        <div className="min-w-0 space-y-6 text-[17px] md:text-lg leading-[1.65] text-neutral-900">
          {children}
        </div>
      </div>
    </section>
  );
}
