"use client";

import { useState, useRef, useCallback, useEffect } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

type CallState = "idle" | "listening" | "processing" | "speaking";

export function VoiceWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isClosed, setIsClosed] = useState(false);
  const [state, setState] = useState<CallState>("idle");
  const [vadProgress, setVadProgress] = useState(0);
  const [displayText, setDisplayText] = useState("");

  const streamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number>(0);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const silenceStartRef = useRef<number>(0);
  const speechDetectedRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sessionIdRef = useRef<string>("");
  const isRecordingRef = useRef(false);
  const chunksRef = useRef<Blob[]>([]);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const speechStartTimeRef = useRef<number>(0);

  const SILENCE_THRESHOLD = 1.5;
  const MIN_SPEECH_MS = 400;

  const cleanup = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
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

  const sendToBackend = useCallback(
    async (audioBlob: Blob) => {
      setState("processing");

      try {
        const formData = new FormData();
        formData.append("audio", audioBlob, "recording.webm");
        formData.append("session_id", sessionIdRef.current);

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

        const userText = resp.headers.get("X-User-Text");
        const agentText = resp.headers.get("X-Agent-Text");
        if (userText) {
          const decoded = decodeURIComponent(userText);
          setDisplayText(decoded);
        }
        if (agentText) {
          const decoded = decodeURIComponent(agentText);
          setDisplayText((prev) => prev + "\n" + decoded);
        }

        const audioBlobResponse = await resp.blob();
        playAudio(audioBlobResponse);
      } catch {
        setDisplayText("Error. Try again.");
        startListening();
      }
    },
    []
  );

  const startListening = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const audioCtx = new AudioContext();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      analyserRef.current = analyser;

      silenceStartRef.current = 0;
      speechDetectedRef.current = false;
      setVadProgress(0);
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
          setVadProgress(0);
        } else {
          if (speechDetectedRef.current) {
            const speechDuration = performance.now() - speechStartTimeRef.current;
            if (speechDuration < MIN_SPEECH_MS) {
              rafRef.current = requestAnimationFrame(checkSilence);
              return;
            }

            if (silenceStartRef.current === 0) {
              silenceStartRef.current = performance.now();
            } else {
              const silenceDuration =
                (performance.now() - silenceStartRef.current) / 1000;
              const progress = Math.min(silenceDuration / SILENCE_THRESHOLD, 1);
              setVadProgress(progress);

              if (silenceDuration >= SILENCE_THRESHOLD) {
                stopRecording();
                return;
              }
            }
          }
        }

        rafRef.current = requestAnimationFrame(checkSilence);
      };

      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/ogg";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      recorderRef.current = recorder;
      isRecordingRef.current = true;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        isRecordingRef.current = false;
        const audioBlob = new Blob(chunksRef.current, { type: mimeType });
        if (audioBlob.size > 1000) {
          await sendToBackend(audioBlob);
        } else {
          startListening();
        }
      };

      recorder.start();
      rafRef.current = requestAnimationFrame(checkSilence);
    } catch {
      setState("idle");
    }
  }, [sendToBackend]);

  const stopRecording = useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
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
    setVadProgress(0);
  }, []);

  const playAudio = useCallback(
    async (audioBlob: Blob) => {
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
        startListening();
      };

      audio.onerror = () => {
        URL.revokeObjectURL(url);
        audioRef.current = null;
        startListening();
      };

      setState("speaking");
      await audio.play();
    },
    [startListening]
  );

  const interrupt = useCallback(() => {
    if (state === "speaking" && audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current.src);
      audioRef.current = null;
      startListening();
    }
  }, [state, startListening]);

  const handleCall = useCallback(() => {
    console.log("Call button clicked");
    sessionIdRef.current = "";
    setDisplayText("");
    startListening();
  }, [startListening]);

  const handleHangUp = useCallback(() => {
    cleanup();
    setIsOpen(false);
    setIsClosed(true);
    setState("idle");
    setDisplayText("");
    setVadProgress(0);
  }, [cleanup]);

  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  if (isClosed) {
    return null;
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 bg-neutral-900 text-white rounded-full w-14 h-14 flex items-center justify-center shadow-lg hover:bg-neutral-800 transition-colors"
        aria-label="Open voice demo"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" x2="12" y1="19" y2="22" />
        </svg>
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-80 bg-white border border-neutral-200 rounded-2xl shadow-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-neutral-900">
          Call with RA-1
        </span>
        <button
          onClick={handleHangUp}
          className="text-neutral-400 hover:text-neutral-600 transition-colors"
          aria-label="Hang up"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
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

      <div
        className="relative w-48 h-48 mx-auto mb-4 cursor-pointer select-none"
        onClick={interrupt}
      >
        <div
          className={`absolute inset-0 rounded-full transition-all duration-300 ${
            state === "listening"
              ? "bg-purple-100"
              : state === "processing"
              ? "bg-amber-100"
              : state === "speaking"
              ? "bg-teal-100"
              : "bg-neutral-100"
          }`}
        />

        {state === "listening" && (
          <>
            <div
              className="absolute inset-4 rounded-full border-2 border-purple-300 animate-ping"
              style={{ animationDuration: "2s" }}
            />
            <div
              className="absolute inset-8 rounded-full border border-purple-200 animate-ping"
              style={{ animationDuration: "2.5s", animationDelay: "0.5s" }}
            />
          </>
        )}

        {state === "speaking" && (
          <div
            className="absolute inset-4 rounded-full border-2 border-teal-300 animate-pulse"
            style={{ animationDuration: "1s" }}
          />
        )}

        <div
          className={`absolute inset-12 rounded-full flex items-center justify-center transition-colors duration-300 ${
            state === "listening"
              ? "bg-purple-500"
              : state === "processing"
              ? "bg-amber-500"
              : state === "speaking"
              ? "bg-teal-500"
              : "bg-neutral-400"
          }`}
        >
          {state === "processing" ? (
            <div className="w-8 h-8 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" x2="12" y1="19" y2="22" />
            </svg>
          )}
        </div>

        {state === "listening" && vadProgress > 0 && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-28 h-1 bg-neutral-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 transition-all duration-100"
              style={{ width: `${vadProgress * 100}%` }}
            />
          </div>
        )}
      </div>

      {displayText && (
        <div className="text-xs text-neutral-500 text-center mb-3 max-h-20 overflow-y-auto whitespace-pre-wrap leading-relaxed">
          {displayText}
        </div>
      )}

      {state === "idle" ? (
        <button
          onClick={handleCall}
          className="w-full py-3 rounded-lg text-sm font-medium bg-green-500 text-white hover:bg-green-600 transition-colors"
        >
          Call
        </button>
      ) : (
        <button
          onClick={handleHangUp}
          className="w-full py-3 rounded-lg text-sm font-medium bg-red-500 text-white hover:bg-red-600 transition-colors"
        >
          Hang Up
        </button>
      )}

      <p className="text-xs text-neutral-400 text-center mt-3">
        {state === "idle" && "Tap Call to start"}
        {state === "listening" && "Listening..."}
        {state === "processing" && "Thinking..."}
        {state === "speaking" && "Tap orb to interrupt"}
      </p>
    </div>
  );
}
