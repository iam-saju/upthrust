"use client";

import { useState, useRef, useCallback, useEffect } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const MAX_RECORDING_SECONDS = 25;

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिंदी" },
  { code: "ml", label: "മലയാളം" },
];

export function VoiceWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [language, setLanguage] = useState("en");
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState("Tap to start");
  const [timeLeft, setTimeLeft] = useState(MAX_RECORDING_SECONDS);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sessionIdRef = useRef<string>("");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (isRecording && timeLeft > 0) {
      timerRef.current = setInterval(() => {
        setTimeLeft((prev) => {
          if (prev <= 1) {
            stopRecording();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRecording]);

  const playAudio = useCallback(async (audioBlob: Blob) => {
    if (audioRef.current) {
      audioRef.current.pause();
      URL.revokeObjectURL(audioRef.current.src);
    }

    const url = URL.createObjectURL(audioBlob);
    const audio = new Audio(url);
    audioRef.current = audio;

    audio.onended = () => {
      URL.revokeObjectURL(url);
      setStatus("Tap to start");
    };

    audio.onerror = () => {
      URL.revokeObjectURL(url);
      setStatus("Playback error. Try again.");
    };

    setStatus("Playing response...");
    await audio.play();
  }, []);

  const sendToBackend = useCallback(
    async (audioBlob: Blob) => {
      const formData = new FormData();
      formData.append("audio", audioBlob, "recording.webm");
      formData.append("language", language);
      formData.append("session_id", sessionIdRef.current);

      try {
        const resp = await fetch(`${BACKEND_URL}/talk`, {
          method: "POST",
          body: formData,
        });

        if (!resp.ok) {
          const errText = await resp.text();
          throw new Error(errText || "Backend error");
        }

        // Capture session ID for conversation memory
        const newSessionId = resp.headers.get("X-Session-ID");
        if (newSessionId) sessionIdRef.current = newSessionId;

        // Stream the audio response
        const audioBlob = await resp.blob();
        await playAudio(audioBlob);
      } catch (err: any) {
        setStatus(err.message || "Error. Try again.");
      } finally {
        setIsProcessing(false);
      }
    },
    [language, playAudio]
  );

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/ogg";
      const recorder = new MediaRecorder(stream, { mimeType });
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        await sendToBackend(audioBlob);
        stream.getTracks().forEach((t) => t.stop());
      };

      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
      setTimeLeft(MAX_RECORDING_SECONDS);
      setStatus(`Listening... ${MAX_RECORDING_SECONDS}s`);
    } catch {
      setStatus("Mic permission denied");
    }
  }, [sendToBackend]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
    setIsProcessing(true);
    setStatus("Processing...");
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const handleClose = useCallback(() => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
    if (audioRef.current) {
      audioRef.current.pause();
    }
    setIsOpen(false);
    setStatus("Tap to start");
    setIsProcessing(false);
    setTimeLeft(MAX_RECORDING_SECONDS);
  }, [isRecording]);

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
    <div className="fixed bottom-6 right-6 z-50 w-72 bg-white border border-neutral-200 rounded-2xl shadow-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-neutral-900">
          Talk to RA-1
        </span>
        <button
          onClick={handleClose}
          className="text-neutral-400 hover:text-neutral-600 transition-colors"
          aria-label="Close"
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

      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        disabled={isRecording || isProcessing}
        className="w-full mb-4 px-3 py-2 text-sm border border-neutral-200 rounded-lg bg-white text-neutral-900 focus:outline-none focus:ring-1 focus:ring-neutral-300 disabled:opacity-50"
      >
        {LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.label}
          </option>
        ))}
      </select>

      <button
        onClick={isRecording ? stopRecording : startRecording}
        disabled={isProcessing}
        className={`w-full py-3 rounded-lg text-sm font-medium transition-colors ${
          isRecording
            ? "bg-red-500 text-white hover:bg-red-600"
            : isProcessing
            ? "bg-neutral-100 text-neutral-400 cursor-not-allowed"
            : "bg-neutral-900 text-white hover:bg-neutral-800"
        }`}
      >
        {isRecording ? `⏹ Stop (${timeLeft}s)` : isProcessing ? "Processing..." : "🎤 Start"}
      </button>

      <p className="text-xs text-neutral-400 text-center mt-3">{status}</p>

      {isRecording && (
        <div className="mt-3 h-1 bg-neutral-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-red-500 transition-all duration-1000 ease-linear"
            style={{ width: `${(timeLeft / MAX_RECORDING_SECONDS) * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}
