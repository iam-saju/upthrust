"use client";

import { useState, useRef, useCallback, useEffect } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type CallState = "idle" | "listening" | "processing" | "speaking";

const LANGUAGES = [
  { code: "en-IN", label: "English", icon: "En" },
  { code: "hi-IN", label: "Hindi", icon: "हि" },
  { code: "ml-IN", label: "Malayalam", icon: "മ" },
  { code: "ta-IN", label: "Tamil", icon: "த" },
];

export function VoiceTerminal() {
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<CallState>("idle");
  const [selectedLang, setSelectedLang] = useState("en-IN");
  const [showDropdown, setShowDropdown] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const silenceStartRef = useRef<number>(0);
  const speechDetectedRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sessionIdRef = useRef<string>("");
  const isRecordingRef = useRef(false);
  const isEndedRef = useRef(false);
  const chunksRef = useRef<Blob[]>([]);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const speechStartTimeRef = useRef<number>(0);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const SILENCE_THRESHOLD = 1.5;
  const MIN_SPEECH_MS = 400;

  const cleanup = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
    }
    if (audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current.src);
    }
    if (recorderRef.current && isRecordingRef.current) {
      try {
        recorderRef.current.stop();
      } catch {}
    }
    streamRef.current = null;
    analyserRef.current = null;
    audioCtxRef.current = null;
    isRecordingRef.current = false;
  }, []);

  const startListening = useCallback(async () => {
    if (isEndedRef.current) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const audioCtx = new AudioContext();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.9;
      source.connect(analyser);
      analyserRef.current = analyser;

      silenceStartRef.current = 0;
      speechDetectedRef.current = false;
      setState("listening");

      const checkSilence = () => {
        if (!analyserRef.current) return;

        const buffer = new Uint8Array(analyserRef.current.fftSize);
        analyserRef.current.getByteTimeDomainData(buffer);

        let sum = 0;
        for (let i = 0; i < buffer.length; i++) {
          const v = (buffer[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buffer.length);

        if (rms > 0.02) {
          if (!speechDetectedRef.current) {
            speechStartTimeRef.current = performance.now();
          }
          silenceStartRef.current = 0;
          speechDetectedRef.current = true;
        } else {
          if (speechDetectedRef.current) {
            const speechDuration =
              performance.now() - speechStartTimeRef.current;
            if (speechDuration < MIN_SPEECH_MS) {
              requestAnimationFrame(checkSilence);
              return;
            }

            if (silenceStartRef.current === 0) {
              silenceStartRef.current = performance.now();
            } else {
              const silenceDuration =
                (performance.now() - silenceStartRef.current) / 1000;

              if (silenceDuration >= SILENCE_THRESHOLD) {
                stopRecording();
                return;
              }
            }
          }
        }

        requestAnimationFrame(checkSilence);
      };

      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/ogg";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorderRef.current = recorder;
      isRecordingRef.current = true;

      const MAX_RECORDING_MS = 15000;
      const recordingTimeout = setTimeout(() => {
        if (isRecordingRef.current) {
          stopRecording();
        }
      }, MAX_RECORDING_MS);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        clearTimeout(recordingTimeout);
        isRecordingRef.current = false;
        if (isEndedRef.current) return;
        const audioBlob = new Blob(chunksRef.current, { type: mimeType });
        if (audioBlob.size > 1000) {
          await sendToBackend(audioBlob);
        } else {
          startListening();
        }
      };

      recorder.start();
      requestAnimationFrame(checkSilence);
    } catch {
      if (!isEndedRef.current) setState("idle");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (recorderRef.current && isRecordingRef.current) {
      recorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
    }
    streamRef.current = null;
    analyserRef.current = null;
    audioCtxRef.current = null;
    isRecordingRef.current = false;
  }, []);

  const sendToBackend = useCallback(
    async (audioBlob: Blob) => {
      if (isEndedRef.current) return;
      setState("processing");

      try {
        const formData = new FormData();
        formData.append("audio", audioBlob, "recording.webm");
        formData.append("session_id", sessionIdRef.current);
        formData.append("language", selectedLang);

        const resp = await fetch(`${BACKEND_URL}/talk`, {
          method: "POST",
          body: formData,
        });

        if (!resp.ok) {
          const errText = await resp.text();
          throw new Error(errText || "Backend error");
        }

        const newSessionId = resp.headers.get("X-Session-ID");
        if (newSessionId) sessionIdRef.current = newSessionId;

        const audioBlobResponse = await resp.blob();
        playAudio(audioBlobResponse);
      } catch {
        if (!isEndedRef.current) {
          startListening();
        }
      }
    },
    [selectedLang]
  );

  const playAudio = useCallback(
    async (audioBlob: Blob) => {
      if (isEndedRef.current) return;
      if (audioRef.current) {
        audioRef.current.pause();
        URL.revokeObjectURL(audioRef.current.src);
      }

      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        if (!isEndedRef.current) startListening();
      };

      audio.onerror = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        if (!isEndedRef.current) startListening();
      };

      setState("speaking");
      await audio.play();
    },
    []
  );

  const handleStart = useCallback(async () => {
    isEndedRef.current = false;
    setState("speaking");

    try {
      const formData = new FormData();
      formData.append("language", selectedLang);

      const resp = await fetch(`${BACKEND_URL}/greet`, {
        method: "POST",
        body: formData,
      });
      const audioBlob = await resp.blob();
      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        if (!isEndedRef.current) startListening();
      };

      audio.onerror = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        if (!isEndedRef.current) startListening();
      };

      await audio.play();
    } catch {
      if (!isEndedRef.current) startListening();
    }
  }, [selectedLang]);

  const handleEnd = useCallback(() => {
    isEndedRef.current = true;
    cleanup();
    setState("idle");
  }, [cleanup]);

  const handleOrbTap = useCallback(() => {
    if (state === "idle") {
      handleStart();
    }
  }, [state, handleStart]);

  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setShowDropdown(false);
      }
    };

    if (showDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDropdown]);

  const isInCall = state !== "idle";

  const statusText =
    state === "idle"
      ? "Tap to start"
      : state === "listening"
      ? "Listening..."
      : state === "processing"
      ? "Thinking..."
      : state === "speaking" && !audioRef.current
      ? "Connecting..."
      : "Speaking...";

  const selectedLangIcon =
    LANGUAGES.find((l) => l.code === selectedLang)?.icon || "En";



  return (
    <div className="pt-6 relative">
      {/* Trigger button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="inline-flex items-center px-4 py-2 rounded-full hover:scale-[1.02]"
          style={{
            background: "transparent",
            border: "1px solid #d4d4d4",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#7a9e7a";
            const textEl = e.currentTarget.querySelector("[data-role='pill-text']");
            if (textEl) textEl.style.color = "#ffffff";
            const circleEl = e.currentTarget.querySelector("[data-role='pill-circle']");
            if (circleEl) circleEl.style.background = "#ffffff";
            const iconEl = e.currentTarget.querySelector("[data-role='pill-icon']");
            if (iconEl) iconEl.setAttribute("stroke", "#7a9e7a");
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
            const textEl = e.currentTarget.querySelector("[data-role='pill-text']");
            if (textEl) textEl.style.color = "#7a9e7a";
            const circleEl = e.currentTarget.querySelector("[data-role='pill-circle']");
            if (circleEl) circleEl.style.background = "#7a9e7a";
            const iconEl = e.currentTarget.querySelector("[data-role='pill-icon']");
            if (iconEl) iconEl.setAttribute("stroke", "#ffffff");
          }}
          aria-label="Open RA-1"
        >
          <span
            data-role="pill-text"
            className="text-[13px] font-normal"
            style={{
              color: "#7a9e7a",
              fontFamily:
                'var(--font-inter), -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif',
            }}
          >
            Try RA-1 beta version
          </span>
          <span
            data-role="pill-circle"
            className="inline-flex items-center justify-center ml-3"
            style={{
              width: "28px",
              height: "28px",
              borderRadius: "50%",
              background: "#7a9e7a",
            }}
          >
            <svg
              data-role="pill-icon"
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#ffffff"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          </span>
        </button>
      )}

      {/* Dialog */}
      {isOpen && (
        <div
          className="w-full max-w-[340px] rounded-xl p-5 relative"
          style={{
            background: "#ffffff",
            border: "1px solid #e5e5e5",
            boxShadow: "0 4px 24px rgba(0,0,0,0.06)",
          }}
        >
          {/* Top bar */}
          <div className="flex items-center justify-between mb-4">
            <span
              className="text-[11px] text-neutral-400"
              style={{
                fontFamily: 'var(--font-inter), -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif',
                letterSpacing: "0.02em",
              }}
            >
              RA-1 · Beta Voice Agent
            </span>

            <div className="flex items-center gap-2">
              {/* Language dropdown - only visible when not in call */}
              {!isInCall && (
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => setShowDropdown(!showDropdown)}
                    className="flex items-center gap-1 text-[11px] text-neutral-500 hover:text-neutral-700 transition-colors"
                    style={{
                      fontFamily: "'Noto Sans Devanagari', 'Noto Sans Malayalam', 'Noto Sans Tamil', 'Noto Sans', system-ui, sans-serif",
                      fontWeight: 700,
                      fontSize: "13px",
                    }}
                  >
                    {selectedLangIcon}
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className={`transition-transform ${showDropdown ? "rotate-180" : ""}`}
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </button>

                  {showDropdown && (
                    <div
                      className="absolute right-0 top-full mt-1 w-36 rounded-lg py-1 z-10"
                      style={{
                        background: "#ffffff",
                        border: "1px solid #e5e5e5",
                        boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
                      }}
                    >
                      {LANGUAGES.map((lang) => (
                        <button
                          key={lang.code}
                          onClick={() => {
                            setSelectedLang(lang.code);
                            setShowDropdown(false);
                          }}
                          className={`w-full text-left px-3 py-2 text-[11px] flex items-center gap-2 transition-colors hover:bg-neutral-50 ${
                            selectedLang === lang.code
                              ? "text-neutral-900 font-medium"
                              : "text-neutral-500"
                          }`}
                          style={{
                            fontFamily: 'var(--font-inter), -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif',
                          }}
                        >
                          <span
                            className="font-bold"
                            style={{
                              minWidth: "18px",
                              textAlign: "center",
                              fontSize: "13px",
                              fontFamily: "'Noto Sans Devanagari', 'Noto Sans Malayalam', 'Noto Sans Tamil', 'Noto Sans', system-ui, sans-serif",
                              fontWeight: 700,
                            }}
                          >
                            {lang.icon}
                          </span>
                          {lang.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Disconnect button - small muted circle, only during call */}
              {isInCall && (
                <button
                  onClick={handleEnd}
                  className="w-7 h-7 rounded-full flex items-center justify-center text-neutral-400 hover:text-red-500 hover:bg-red-50/60 transition-colors"
                  aria-label="Disconnect"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-18.67-18.67 2 2 0 0 1 2-2.18h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L7.1 10.68a16 16 0 0 0 3.58 2.63z" />
                    <line x1="1" x2="23" y1="1" y2="23" />
                  </svg>
                </button>
              )}
            </div>
          </div>

          {/* Orb */}
          <div className="flex justify-center mb-2">
            <button
              key={state}
              onClick={handleOrbTap}
              className={`w-[120px] h-[120px] rounded-full relative transition-all duration-500 ${
                state === "idle"
                  ? ""
                  : state === "listening"
                  ? "animate-orb-listen"
                  : "animate-orb-speak"
              }`}
              style={{
                background:
                  "radial-gradient(circle at 35% 35%, #e8c97a 0%, #c97a3a 40%, #8b4a1a 100%)",
                border: "none",
                cursor: state === "idle" ? "pointer" : "default",
              }}
              aria-label={state === "idle" ? "Tap to start" : "RA-1 active"}
            />
          </div>

          {/* Status */}
          <p
            className="text-center text-[12px] text-neutral-400 mb-4"
            style={{
              fontFamily: 'var(--font-inter), -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif',
            }}
          >
            {statusText}
          </p>

          {/* Close button - bottom right corner */}
          <button
            onClick={() => { handleEnd(); setIsOpen(false); }}
            className="absolute bottom-3 right-3 w-6 h-6 flex items-center justify-center text-neutral-300 hover:text-neutral-500 transition-colors"
            aria-label="Close dialog"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" x2="6" y1="6" y2="18" />
              <line x1="6" x2="18" y1="6" y2="18" />
            </svg>
          </button>
        </div>
      )}

      <style jsx>{`
        @keyframes orb-listen {
          0%,
          100% {
            transform: scale(1);
            opacity: 0.9;
          }
          50% {
            transform: scale(1.06);
            opacity: 1;
          }
        }

        @keyframes orb-speak {
          0% {
            transform: scale(1) rotate(0deg);
          }
          25% {
            transform: scale(1.03) rotate(0.5deg);
          }
          50% {
            transform: scale(1.06) rotate(0deg);
          }
          75% {
            transform: scale(1.03) rotate(-0.5deg);
          }
          100% {
            transform: scale(1) rotate(0deg);
          }
        }

        .animate-orb-listen {
          animation: orb-listen 1.5s ease-in-out infinite;
        }

        .animate-orb-speak {
          animation: orb-speak 1.2s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}
