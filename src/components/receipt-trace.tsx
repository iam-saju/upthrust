import type { ReactNode } from "react";

export function ReceiptTrace({ children }: { children: ReactNode }) {
  return (
    <div aria-hidden className="receipt-fragment">
      {children}
    </div>
  );
}
