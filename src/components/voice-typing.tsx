"use client";

import { useState, useEffect, useRef, useSyncExternalStore } from "react";

const DEFAULT_WORDS = [
  "hello",
  "നമസ്കാരം",
  "haan ji",
  "வணக்கம்",
  "ঠিক আছে",
  "hello?",
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

export function VoiceTyping({
  words = DEFAULT_WORDS,
  className = "",
}: { words?: string[]; className?: string }) {
  const isServer = useSyncExternalStore(emptySubscribe, getSnapshot, getServerSnapshot);
  const [currentText, setCurrentText] = useState("");

  const cancelledRef = useRef(false);
  const wordIndexRef = useRef(0);
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

    function schedule(
      fn: () => void,
      delay: number,
    ): ReturnType<typeof setTimeout> {
      return setTimeout(() => {
        if (!cancelledRef.current) fn();
      }, delay);
    }

    function cycleWord(word: string, step: number): void {
      const graphemes = getGraphemes(word);
      const total = graphemes.length;

      if (step < total) {
        setCurrentText(graphemes.slice(0, step + 1).join(""));
        const hesitation = Math.random() < 0.05 ? 400 : 0;
        const delay = randomBetween(80, 150) + hesitation;
        schedule(() => cycleWord(word, step + 1), delay);
        return;
      }

      if (step === total) {
        const holdDelay = randomBetween(3500, 5500);
        schedule(() => cycleWord(word, step + 1), holdDelay);
        return;
      }

      if (step < total * 2) {
        const remaining = total - (step - total) - 1;
        setCurrentText(graphemes.slice(0, remaining).join(""));
        const delay = randomBetween(40, 90);
        schedule(() => cycleWord(word, step + 1), delay);
        return;
      }

      setCurrentText("");
      const nextWordIndex = (wordIndexRef.current + 1) % words.length;
      wordIndexRef.current = nextWordIndex;
      const gapDelay = randomBetween(400, 700);
      schedule(() => cycleWord(words[nextWordIndex], 0), gapDelay);
    }

    const initialDelay = randomBetween(1000, 2000);
    const id = schedule(() => cycleWord(words[0], 0), initialDelay);

    return () => {
      cancelledRef.current = true;
      clearTimeout(id);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (isServer) {
    return (
      <span aria-hidden className={`voice-layer ${className}`} style={{ display: 'inline-block', minWidth: '140px' }}>
        {words[0]}
      </span>
    );
  }

  return (
    <span aria-hidden className={`voice-layer ${className}`} style={{ display: 'inline-block', minWidth: '140px' }}>
      {currentText}
      {currentText !== "" && <span className="voice-cursor">▎</span>}
    </span>
  );
}
