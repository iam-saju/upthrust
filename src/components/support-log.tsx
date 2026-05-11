"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";

const PHRASES = [
  "haan checking now",
  "ട്രാക്കിംഗ് അയച്ചിട്ടുണ്ട്",
  "refund process aaguthu",
  "സാർ OTP പറയാമോ",
  "एक मिनट",
  "பணம் வந்தாச்சு",
  "link bhej diya",
  "കേൾക്കുന്നുണ്ടോ",
  "கால் கட் ஆயிடுச்சு",
  "भुगतान आ गया",
  "delivery എത്തി sir",
  "இப்போ பார்க்கிறேன்",
  "call reconnect ho raha hai",
  "अभी चेक करता हूँ",
  "ഒരു മിനിറ്റ്",
  "आवाज़ आ रही है",
  "one minute chetta",
  "voice clear aa?",
  "വിളി കട്ട് ആയി",
  "कॉल कट गया",
];

const emptySubscribe = () => () => {};
function getSnapshot() {
  return false;
}
function getServerSnapshot() {
  return true;
}

function randomBetween(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function toGraphemes(word: string): string[] {
  try {
    const segmenter = new Intl.Segmenter("en", { granularity: "grapheme" });
    return [...segmenter.segment(word)].map((s) => s.segment);
  } catch {
    return Array.from(word);
  }
}

function pickRandom(exclude: number): number {
  let next: number;
  do {
    next = Math.floor(Math.random() * PHRASES.length);
  } while (next === exclude && PHRASES.length > 1);
  return next;
}

export function SupportLog() {
  const isServer = useSyncExternalStore(emptySubscribe, getSnapshot, getServerSnapshot);
  const [currentText, setCurrentText] = useState("");

  const cancelledRef = useRef(false);
  const phraseIndexRef = useRef(0);
  const graphemeCacheRef = useRef<Map<string, string[]>>(new Map());

  function getGraphemes(word: string): string[] {
    let cached = graphemeCacheRef.current.get(word);
    if (!cached) {
      cached = toGraphemes(word);
      graphemeCacheRef.current.set(word, cached);
    }
    return cached;
  }

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    cancelledRef.current = false;
    phraseIndexRef.current = pickRandom(-1);

    function cyclePhrase(
      phrase: string,
      step: number,
    ): ReturnType<typeof setTimeout> | null {
      if (cancelledRef.current) return null;

      const graphemes = getGraphemes(phrase);
      const total = graphemes.length;

      if (step < total) {
        setCurrentText(graphemes.slice(0, step + 1).join(""));
        const hesitation = Math.random() < 0.05 ? 300 : 0;
        const delay = randomBetween(60, 120) + hesitation;
        return setTimeout(() => cyclePhrase(phrase, step + 1), delay);
      }

      if (step === total) {
        const holdDelay = randomBetween(1500, 2500);
        return setTimeout(() => cyclePhrase(phrase, step + 1), holdDelay);
      }

      if (step < total * 2) {
        const remaining = total - (step - total) - 1;
        setCurrentText(graphemes.slice(0, remaining).join(""));
        const delay = randomBetween(30, 80);
        return setTimeout(() => cyclePhrase(phrase, step + 1), delay);
      }

      setCurrentText("");
      const nextIndex = pickRandom(phraseIndexRef.current);
      phraseIndexRef.current = nextIndex;
      const gapDelay = randomBetween(400, 700);
      return setTimeout(() => cyclePhrase(PHRASES[nextIndex], 0), gapDelay);
    }

    const startDelay = randomBetween(800, 1500);
    const initialTimeout = setTimeout(
      () => cyclePhrase(PHRASES[phraseIndexRef.current], 0),
      startDelay,
    );

    return () => {
      cancelledRef.current = true;
      clearTimeout(initialTimeout);
    };
  }, []);

  if (isServer) {
    return (
      <div aria-hidden className="support-log">
        {PHRASES[0]}
      </div>
    );
  }

  return (
    <div aria-hidden className="support-log">
      <span>
        {currentText}
        {currentText !== "" && <span className="voice-cursor">▎</span>}
      </span>
    </div>
  );
}
