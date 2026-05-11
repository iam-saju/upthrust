"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";

const EXCHANGES = [
  { customer: "റീഫണ്ട് കിട്ടിയില്ല.", agent: "24 മണിക്കൂറിനുള്ളിൽ ക്രെഡിറ്റ് ആവുമ്മാ." },
  { customer: "OTP വന്നില്ല.", agent: "ഒരു മിനിറ്റ്, റീസെൻഡ് ചെയ്യാം." },
  { customer: "பார்சல் இன்னும் வரல.", agent: "செக் பண்ணிட்டு கால் பண்ணறேன் சார்." },
  { customer: "கால் கட் ஆயிடுச்சு.", agent: "நான் லைன்ல இருக்கேன், சொல்லுங்க." },
  { customer: "पेमेंट कट गया.", agent: "रिफंड शुरू कर दिया है सर." },
  { customer: "OTP नहीं आया.", agent: "एक मिनट, फिर से भेजता हूँ." },
  { customer: "OTP రాలేదు.", agent: "ఒక్కసారి రీసెండ్ చేస్తాను సార్." },
  { customer: "డెలివరీ ఇంకా రాలేదు.", agent: "చెక్ చేసి అప్డేట్ చెప్తాను మేడమ్." },
  { customer: "refund kittiyilla.", agent: "24 hours ullil credit aavum ma'am." },
  { customer: "parcel innum varala.", agent: "check pannitu call back panren sir." },
  { customer: "payment deduct ho gaya.", agent: "refund already initiate kar diya hai." },
  { customer: "OTP raaledu.", agent: "okasari resend chesthanu sir." },
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

    const INITIAL_DELAY = 900;
    const WORD_DELAY = 140;
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const renderAgentWords = () => {
    return agentWords.map((word, index) => (
      <span
        key={index}
        className="support-word"
        style={{
          opacity: index < visibleWords ? 1 : 0,
          transform: index < visibleWords ? "translateY(0)" : "translateY(4px)",
          filter: index < visibleWords ? "blur(0)" : "blur(2px)",
          transition: "opacity 260ms cubic-bezier(.22,.61,.36,1), transform 260ms cubic-bezier(.22,.61,.36,1), filter 260ms cubic-bezier(.22,.61,.36,1)",
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
