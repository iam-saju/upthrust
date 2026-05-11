"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";

const EXCHANGES = [
  { customer: "refund process aaguthu?", agent: "haan sir, initiated." },
  { customer: "call cut aayiduchu…", agent: "naan line la iruken sir." },
  { customer: "OTP vannilla.", agent: "oru minute chetta, resend cheyyam." },
  { customer: "payment deduct ho gaya.", agent: "refund 24 hours mein aa jayega." },
  { customer: "order ta ekhono asheni.", agent: "check kore bolchi dada." },
  { customer: "sir OTP vannille…", agent: "resend cheythu chetta." },
  { customer: "tracking number ethra?", agent: "share cheyyam sir." },
  { customer: "product damage aayittund.", agent: "photo ayakkam ma'am." },
];

const emptySubscribe = () => () => {};
function getSnapshot() {
  return false;
}
function getServerSnapshot() {
  return true;
}

function pickRandom(exclude: number): number {
  let next: number;
  do {
    next = Math.floor(Math.random() * EXCHANGES.length);
  } while (next === exclude && EXCHANGES.length > 1);
  return next;
}

export function SupportLog() {
  const isServer = useSyncExternalStore(emptySubscribe, getSnapshot, getServerSnapshot);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [opacity, setOpacity] = useState(1);

  const cancelledRef = useRef(false);
  const indexRef = useRef(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    cancelledRef.current = false;
    indexRef.current = pickRandom(-1);
    setCurrentIndex(indexRef.current);

    const HOLD_TIME = 3500; // 3.5s display
    const FADE_OUT_TIME = 800; // 800ms fade out
    const GAP_TIME = 400; // 400ms gap

    function cycleExchange(): void {
      if (cancelledRef.current) return;

      // Start fade out after hold time
      setTimeout(() => {
        if (cancelledRef.current) return;
        setOpacity(0);

        // After fade out + gap, switch and fade in
        setTimeout(() => {
          if (cancelledRef.current) return;
          const nextIndex = pickRandom(indexRef.current);
          indexRef.current = nextIndex;
          setCurrentIndex(nextIndex);
          setOpacity(1);

          // Schedule next cycle
          setTimeout(cycleExchange, HOLD_TIME);
        }, FADE_OUT_TIME + GAP_TIME);
      }, HOLD_TIME);
    }

    // Start first cycle
    const initialTimeout = setTimeout(cycleExchange, HOLD_TIME);

    return () => {
      cancelledRef.current = true;
      clearTimeout(initialTimeout);
    };
  }, []);

  const currentExchange = EXCHANGES[currentIndex];

  if (isServer) {
    return (
      <div aria-hidden className="support-log">
        <div className="support-exchange">
          <div className="support-line">
            <span className="support-label">customer:</span>
            <span className="support-customer">{EXCHANGES[0].customer}</span>
          </div>
          <div className="support-line">
            <span className="support-label">agent:</span>
            <span className="support-agent">{EXCHANGES[0].agent}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div aria-hidden className="support-log">
      <div 
        className="support-exchange"
        style={{ opacity, transition: "opacity 800ms ease-in-out" }}
      >
        <div className="support-line">
          <span className="support-label">customer:</span>
          <span className="support-customer">{currentExchange.customer}</span>
        </div>
        <div className="support-line">
          <span className="support-label">agent:</span>
          <span className="support-agent">{currentExchange.agent}</span>
        </div>
      </div>
    </div>
  );
}
