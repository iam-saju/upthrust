"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";

const EXCHANGES = [
  { customer: "Refund കിട്ടിയില്ല.", agent: "24 hours ഉള്ളിൽ credit ആവും ma'am." },
  { customer: "Parcel இன்னும் வரல.", agent: "Hub la iruku sir, today deliver ஆகிடும்." },
  { customer: "Payment deduct ho gaya but order confirm nahi hua.", agent: "Amount hold pe hai sir, automatically reverse ho jayega." },
  { customer: "OTP ఇంకా రాలేదు.", agent: "Network slow ఉంది ma'am, resend chesthanu." },
  { customer: "പ്രൊഡക്ട് ഡാമേജ് ആയി വന്നു.", agent: "Photo അയച്ചാൽ replacement arrange ചെയ്യാം." },
  { customer: "கால் கட் ஆயிடுச்சு.", agent: "நான் இன்னும் lineல இருக்கேன் sir, சொல்லுங்க." },
  { customer: "Address galat update ho gaya.", agent: "Tension mat lijiye, delivery se pehle change kar deta hoon." },
  { customer: "Delivery chaala late ayyindi.", agent: "Rider nearby unnadu sir, 10 minutes lo reach avthadu." },
  { customer: "Tracking update আসছে না.", agent: "Courier side delay ache, ami check kore bolchi." },
  { customer: "Can I speak to a real person?", agent: "I'll connect you to our support lead right away." },
];

const emptySubscribe = () => () => {};
function getSnapshot() { return false; }
function getServerSnapshot() { return true; }

function toGraphemes(text: string): string[] {
  try {
    const segmenter = new Intl.Segmenter("en", { granularity: "grapheme" });
    return [...segmenter.segment(text)].map((s) => s.segment);
  } catch {
    return Array.from(text);
  }
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
  const [visibleChars, setVisibleChars] = useState(0);
  const [isFadingOut, setIsFadingOut] = useState(false);

  const cancelledRef = useRef(false);
  const indexRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentExchange = EXCHANGES[currentIndex];
  const agentGraphemes = toGraphemes(currentExchange.agent);

  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    cancelledRef.current = false;
    indexRef.current = pickRandom(-1);

    const LISTEN_TIME = 900;
    const CHAR_DELAY = 60;
    const HOLD_TIME = 3000;
    const FADE_OUT_TIME = 600;

    function clearCurrentTimeout() {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    }

    function animateResponse(): void {
      if (cancelledRef.current) return;

      let charIndex = 0;
      setVisibleChars(0);
      setIsFadingOut(false);

      timeoutRef.current = setTimeout(() => {
        if (cancelledRef.current) return;

        function revealNextChar(): void {
          if (cancelledRef.current) return;

          if (charIndex < agentGraphemes.length) {
            setVisibleChars(charIndex + 1);
            charIndex++;
            const hesitation = Math.random() < 0.1 ? 80 : 0;
            timeoutRef.current = setTimeout(revealNextChar, CHAR_DELAY + hesitation);
          } else {
            timeoutRef.current = setTimeout(() => {
              if (cancelledRef.current) return;
              setIsFadingOut(true);
              timeoutRef.current = setTimeout(() => {
                if (cancelledRef.current) return;
                const nextIndex = pickRandom(indexRef.current);
                indexRef.current = nextIndex;
                setCurrentIndex(nextIndex);
                timeoutRef.current = setTimeout(animateResponse, 100);
              }, FADE_OUT_TIME);
            }, HOLD_TIME);
          }
        }

        revealNextChar();
      }, LISTEN_TIME);
    }

    animateResponse();

    return () => {
      cancelledRef.current = true;
      clearCurrentTimeout();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const renderAgentChars = () => {
    return agentGraphemes.map((char, index) => (
      <span
        key={index}
        className="support-char"
        style={{
          opacity: index < visibleChars ? 1 : 0,
          transform: index < visibleChars ? "translateY(0)" : "translateY(3px)",
          filter: index < visibleChars ? "blur(0)" : "blur(3px)",
          transition: "opacity 260ms cubic-bezier(.22,.61,.36,1), transform 260ms cubic-bezier(.22,.61,.36,1), filter 260ms cubic-bezier(.22,.61,.36,1)",
          display: "inline-block",
        }}
      >
        {char}
      </span>
    ));
  };

  if (isServer) {
    const firstExchange = EXCHANGES[0];
    return (
      <div aria-hidden className="support-log">
        <div className="support-exchange">
          <p className="support-customer">{'\u201C'}{firstExchange.customer}{'\u201D'}</p>
          <p className="support-agent">{firstExchange.agent}</p>
        </div>
      </div>
    );
  }

  return (
    <div 
      aria-hidden 
      className="support-log"
      style={{
        opacity: isFadingOut ? 0 : 1,
        transition: "opacity 600ms ease-out",
      }}
    >
      <div className="support-exchange">
        <p className="support-customer">{'\u201C'}{currentExchange.customer}{'\u201D'}</p>
        <p className="support-agent">{renderAgentChars()}</p>
      </div>
    </div>
  );
}
