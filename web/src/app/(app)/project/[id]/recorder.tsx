"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { Teleprompter } from "./teleprompter";

/** In-browser A-roll capture (getUserMedia + MediaRecorder). The engine re-normalizes
 *  to 1080×1920/60fps CFR, so the exact webcam resolution doesn't need to be perfect. */
export function Recorder({ onRecorded }: { onRecorded: (blob: Blob) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    navigator.mediaDevices
      .getUserMedia({
        video: { width: { ideal: 1080 }, height: { ideal: 1920 }, facingMode: "user" },
        audio: { echoCancellation: true, noiseSuppression: true },
      })
      .then((stream) => {
        if (!active) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch((e) => setError(e instanceof Error ? e.message : "camera unavailable"));
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (!recording) return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [recording]);

  function toggle() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    if (!streamRef.current) return;
    chunks.current = [];
    setSeconds(0);
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
      ? "video/webm;codecs=vp9,opus"
      : "video/webm";
    const rec = new MediaRecorder(streamRef.current, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data);
    };
    rec.onstop = () => onRecorded(new Blob(chunks.current, { type: "video/webm" }));
    recorderRef.current = rec;
    rec.start();
    setRecording(true);
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300">
        Camera/mic unavailable: {error}. You can upload a file instead.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Teleprompter recording={recording} />
      <div className="relative mx-auto aspect-[9/16] max-w-[240px] overflow-hidden rounded-2xl border border-white/10 bg-black">
        <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-cover" />
        {recording && (
          <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-xs">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse-dot" />
            {Math.floor(seconds / 60)}:{(seconds % 60).toString().padStart(2, "0")}
          </div>
        )}
      </div>
      <Button onClick={toggle} variant={recording ? "outline" : "primary"} className="w-full">
        {recording ? "Stop recording" : "Start recording"}
      </Button>
      <p className="text-center text-xs text-white/35">
        Keep talking through mistakes — Cadence removes silence, fillers, and bad takes.
      </p>
    </div>
  );
}
