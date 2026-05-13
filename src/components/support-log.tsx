"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";

const EXCHANGES = [
  { customer: "റീഫണ്ട് കിട്ടിയില്ല.", agent: "റീഫണ്ട് initiate ചെയ്തിട്ടുണ്ട് ma'am." },
  { customer: "OTP വന്നില്ല.", agent: "ഒരു മിനിറ്റ്, resend ചെയ്യാം." },
  { customer: "refund kittiyilla.", agent: "24 hours ullil credit aavum." },
  { customer: "tracking update vannilla.", agent: "rider nearby undu sir." },
  { customer: "பார்சல் இன்னும் வரல.", agent: "இன்னைக்கு deliver ஆகிடும் ma'am." },
  { customer: "கால் கட் ஆயிடுச்சு.", agent: "நான் lineல இருக்கேன் சொல்லுங்க." },
  { customer: "payment twice deduct ஆயிடுச்சு.", agent: "refund process start panniyachu sir." },
  { customer: "app open ஆகல.", agent: "update pannitu once try pannunga." },
  { customer: "पेमेंट कट गया.", agent: "रिफंड शुरू कर दिया है sir." },
  { customer: "OTP नहीं आया.", agent: "एक मिनट, फिर से भेजता हूँ." },
  { customer: "address galat update ho gaya.", agent: "delivery se pehle correct kar deta hoon." },
  { customer: "delivery bahut late hai.", agent: "rider nearby hai ma'am." },
  { customer: "డెలివరీ ఇంకా రాలేదు.", agent: "చెక్ చేసి update చెప్తాను." },
  { customer: "OTP రాలేదు.", agent: "ఒక్కసారి resend చేస్తాను sir." },
  { customer: "payment rendu saarlu cut ayyindi.", agent: "refund already initiate ayyindi." },
  { customer: "call disconnect ayyindi.", agent: "line lo ne unnanu ma'am." },
  { customer: "order ekhono arrive hoyni.", agent: "check kore update dicchi." },
  { customer: "payment cut ಆಗಿದೆ.", agent: "refund process start ಮಾಡಿದ್ದೇವೆ sir." },
];

const emptySubscribe = () => () => {};
function getSnapshot() { return false; }
function getServerSnapshot() { return true; }

function toWords(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
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

    const LISTEN_TIME = 900;
    const WORD_DELAY = 140;
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

      let wordIndex = 0;
      setVisibleWords(0);
      setIsFadingOut(false);

      timeoutRef.current = setTimeout(() => {
        if (cancelledRef.current) return;

        function revealNextWord(): void {
          if (cancelledRef.current) return;

          if (wordIndex < agentWords.length) {
            setVisibleWords(wordIndex + 1);
            wordIndex++;
            const hesitation = Math.random() < 0.1 ? 60 : 0;
            timeoutRef.current = setTimeout(revealNextWord, WORD_DELAY + hesitation);
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

        revealNextWord();
      }, LISTEN_TIME);
    }

    animateResponse();

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
          transform: index < visibleWords ? "translateY(0)" : "translateY(3px)",
          filter: index < visibleWords ? "blur(0)" : "blur(3px)",
          transition: "opacity 260ms cubic-bezier(.22,.61,.36,1), transform 260ms cubic-bezier(.22,.61,.36,1), filter 260ms cubic-bezier(.22,.61,.36,1)",
          display: "inline-block",
          marginRight: "0.35em",
        }}
      >
        {word}
      </span>
    ));
  };

  if (isServer) {
    return (
      <div aria-hidden className="support-log">
        <div className="support-exchange">
          <p className="support-customer" style={{ opacity: 0 }}>
            <span style={{ display: "inline-block", width: "8em", height: "1em", background: "rgba(0,0,0,0.06)", borderRadius: "2px" }} />
          </p>
          <p className="support-agent" style={{ opacity: 0 }}>
            <span style={{ display: "inline-block", width: "12em", height: "1em", background: "rgba(0,0,0,0.06)", borderRadius: "2px" }} />
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
        <p className="support-customer">{currentExchange.customer}</p>
        <p className="support-agent">{renderAgentWords()}</p>
      </div>
    </div>
  );
}
