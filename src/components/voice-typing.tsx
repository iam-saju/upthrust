"use client";

import { useEffect, useRef, useState } from "react";

const DEFAULT_WORDS = [
  "hello",
  "നമസ്കാരം",
  "haan ji",
  "வணக்கம்",
  "ঠিক আছে",
  "hello?",
];

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
  const [currentText, setCurrentText] = useState(words[0] ?? "");

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

    function cycleWord(word: string, phase: string, index: number): void {
      const graphemes = getGraphemes(word);
      const total = graphemes.length;

      if (phase === "typing") {
        if (index < total) {
          setCurrentText(graphemes.slice(0, index + 1).join(""));
          const hesitation = Math.random() < 0.05 ? 400 : 0;
          const delay = randomBetween(80, 150) + hesitation;
          schedule(() => cycleWord(word, "typing", index + 1), delay);
          return;
        }
        const holdDelay = randomBetween(3500, 5500);
        schedule(() => cycleWord(word, "deleting", total), holdDelay);
        return;
      }

      if (phase === "deleting") {
        if (index > 0) {
          setCurrentText(graphemes.slice(0, index - 1).join(""));
          const delay = randomBetween(40, 90);
          schedule(() => cycleWord(word, "deleting", index - 1), delay);
          return;
        }
        setCurrentText("");
        const nextWordIndex = (wordIndexRef.current + 1) % words.length;
        wordIndexRef.current = nextWordIndex;
        const gapDelay = randomBetween(400, 700);
        schedule(() => cycleWord(words[nextWordIndex], "typing", 0), gapDelay);
        return;
      }
    }

    const initialWord = words[0] ?? "";
    const initialGraphemes = getGraphemes(initialWord);
    const initialDelay = randomBetween(1600, 2600);
    const id = schedule(
      () => cycleWord(initialWord, "deleting", initialGraphemes.length),
      initialDelay,
    );

    return () => {
      cancelledRef.current = true;
      clearTimeout(id);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <span
      aria-hidden
      className={`voice-layer ${className}`}
      style={{ display: "inline-block", minWidth: "140px" }}
      data-voice-typing
    >
      {currentText}
      {currentText !== "" && <span className="voice-cursor">▎</span>}
    </span>
  );
}
