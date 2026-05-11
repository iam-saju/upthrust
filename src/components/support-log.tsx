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
function getSnapshot() { return false; }
function getServerSnapshot() { return true; }

function toWords(text: string): string[] {
  try {
    const segmenter = new Intl.Segmenter("en", { granularity: "word" });
    return [...segmenter.segment(text)]
      .filter((s) => s.isWordLike)
      .map((s) => s.segment);
  } catch {
    return text.split(/\s+/);
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
  const [visibleWords, setVisibleWords] = useState(0);
  const [isFadingOut, setIsFadingOut] = useState(false);

  const cancelledRef = useRef(false);
  const indexRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentExchange = EXCHANGES[currentIndex];
  const agentWords = toWords(currentExchange.agent);

  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    cancelledRef.current = false;
    indexRef.current = pickRandom(-1);

    const INITIAL_DELAY = 400;
    const WORD_DELAY = 120;
    const HOLD_TIME = 3000;
    const FADE_OUT_TIME = 600;

    function clearCurrentTimeout() {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    }

    function animateWords(): void {
      if (cancelledRef.current) return;

      let wordIndex = 0;
      setVisibleWords(0);
      setIsFadingOut(false);

      function revealNextWord(): void {
        if (cancelledRef.current) return;

        if (wordIndex < agentWords.length) {
          setVisibleWords(wordIndex + 1);
          wordIndex++;
          timeoutRef.current = setTimeout(revealNextWord, WORD_DELAY);
        } else {
          timeoutRef.current = setTimeout(() => {
            if (cancelledRef.current) return;
            setIsFadingOut(true);
            timeoutRef.current = setTimeout(() => {
              if (cancelledRef.current) return;
              const nextIndex = pickRandom(indexRef.current);
              indexRef.current = nextIndex;
              setCurrentIndex(nextIndex);
              timeoutRef.current = setTimeout(animateWords, INITIAL_DELAY);
            }, FADE_OUT_TIME);
          }, HOLD_TIME);
        }
      }

      timeoutRef.current = setTimeout(revealNextWord, INITIAL_DELAY);
    }

    timeoutRef.current = setTimeout(animateWords, INITIAL_DELAY);

    return () => {
      cancelledRef.current = true;
      clearCurrentTimeout();
    };
  }, [agentWords.length]);

  const renderAgentWords = () => {
    return agentWords.map((word, index) => (
      <span
        key={index}
        className="support-word"
        style={{
          opacity: index < visibleWords ? 1 : 0,
          transform: index < visibleWords ? "translateY(0)" : "translateY(2px)",
          transition: `opacity 400ms ease-out, transform 400ms ease-out`,
          display: "inline-block",
          marginRight: "0.25em",
        }}
      >
        {word}
      </span>
    ));
  };

  if (isServer) {
    const firstExchange = EXCHANGES[0];
    const firstWords = toWords(firstExchange.agent);
    return (
      <div aria-hidden className="support-log">
        <div className="support-exchange">
          <p className="support-customer">{'\u201C'}{firstExchange.customer}{'\u201D'}</p>
          <p className="support-agent">
            {firstWords.map((word, i) => (
              <span key={i} className="support-word" style={{ marginRight: "0.25em" }}>
                {word}
              </span>
            ))}
          </p>
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
        <p className="support-agent">{renderAgentWords()}</p>
      </div>
    </div>
  );
}
