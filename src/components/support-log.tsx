"use client";

import { useEffect, useRef, useState } from "react";

type Exchange = {
  customer: string;
  agent: string;
};

type SupportLogProps = {
  exchanges?: Exchange[];
  theme?: "light" | "dark";
};

const DEFAULT_EXCHANGES: Exchange[] = [
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

function pickRandom(length: number, exclude: number) {
  if (length <= 1) return 0;

  let next = exclude;
  while (next === exclude) {
    next = Math.floor(Math.random() * length);
  }
  return next;
}

function toGraphemes(value: string): string[] {
  try {
    const segmenter = new Intl.Segmenter("en", { granularity: "grapheme" });
    return [...segmenter.segment(value)].map((segment) => segment.segment);
  } catch {
    return Array.from(value);
  }
}

export function SupportLog({
  exchanges = DEFAULT_EXCHANGES,
  theme = "light",
}: SupportLogProps) {
  const safeExchanges = exchanges.length > 0 ? exchanges : DEFAULT_EXCHANGES;
  const [currentIndex, setCurrentIndex] = useState(0);
  const [typedAgent, setTypedAgent] = useState("");
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentExchange = safeExchanges[currentIndex] ?? safeExchanges[0];

  useEffect(() => {
    timeoutRef.current = setTimeout(() => {
      setCurrentIndex((previous) => pickRandom(safeExchanges.length, previous));
    }, 4200);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    };
  }, [currentIndex, safeExchanges.length]);

  useEffect(() => {
    const timeouts: ReturnType<typeof setTimeout>[] = [];

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      timeouts.push(setTimeout(() => setTypedAgent(currentExchange.agent), 0));
      return () => {
        timeouts.forEach(clearTimeout);
      };
    }

    const graphemes = toGraphemes(currentExchange.agent);
    timeouts.push(setTimeout(() => setTypedAgent(""), 0));

    graphemes.forEach((_, index) => {
      const timeout = setTimeout(() => {
        setTypedAgent(graphemes.slice(0, index + 1).join(""));
      }, 320 + index * 72);
      timeouts.push(timeout);
    });

    return () => {
      timeouts.forEach(clearTimeout);
    };
  }, [currentExchange.agent]);

  return (
    <div
      aria-hidden
      className="support-log"
      data-theme={theme}
    >
      <div className="support-exchange">
        <p className="support-customer">
          {currentExchange.customer}
        </p>
        <p className="support-agent">
          {typedAgent}
          {typedAgent !== "" && typedAgent !== currentExchange.agent && (
            <span className="voice-cursor">▎</span>
          )}
        </p>
      </div>
    </div>
  );
}
