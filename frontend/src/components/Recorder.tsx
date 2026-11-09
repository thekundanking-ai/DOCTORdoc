import { useEffect, useRef, useState } from "react";

type Props = {
  onSubmit: (blob: Blob, durationSeconds: number) => Promise<void>;
  onBack: () => void;
};

type Phase = "idle" | "requesting" | "recording" | "preview" | "submitting";

function formatTime(total: number): string {
  const m = Math.floor(total / 60).toString().padStart(2, "0");
  const s = (total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function Recorder({ onSubmit, onBack }: Props) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [recorded, setRecorded] = useState<Blob | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const secondsRef = useRef(0);

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      stopTimer();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  async function startRecording() {
    setError(null);
    setSeconds(0);
    secondsRef.current = 0;
    setPhase("requesting");
    try {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        throw new Error("Recording is not supported in this browser.");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/wav"];
      const mime =
        (typeof MediaRecorder.isTypeSupported === "function" &&
          preferred.find((t) => MediaRecorder.isTypeSupported(t))) ||
        "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType: mime });
      recorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime });
        stopTimer();
        stream.getTracks().forEach((track) => track.stop());
        if (blob.size === 0) {
          setError("Recording produced empty audio.");
          setPhase("idle");
          return;
        }
        setRecorded(blob);
        setPreviewUrl(URL.createObjectURL(blob));
        setPhase("preview");
      };

      recorder.start();
      setPhase("recording");
      timerRef.current = window.setInterval(() => {
        secondsRef.current += 1;
        setSeconds(secondsRef.current);
      }, 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cannot access microphone.");
      setPhase("idle");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
  }

  function discard() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setRecorded(null);
    setSeconds(0);
    secondsRef.current = 0;
    setError(null);
    setPhase("idle");
  }

  async function submit() {
    if (!recorded) return;
    setPhase("submitting");
    setError(null);
    try {
      await onSubmit(recorded, seconds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setPhase("preview");
    }
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {phase === "idle" && (
        <div className="flex gap-2">
          <button onClick={() => void startRecording()} className="bg-red-600 text-white rounded px-4 py-2">
            Start recording
          </button>
          <button onClick={onBack} className="border rounded px-4 py-2">
            Back
          </button>
        </div>
      )}

      {phase === "requesting" && <p>Requesting microphone…</p>}

      {phase === "recording" && (
        <div className="space-y-3">
          <p className="font-mono text-xl">{formatTime(seconds)}</p>
          <p className="text-red-600">● Recording…</p>
          <button onClick={stopRecording} className="bg-gray-800 text-white rounded px-4 py-2">
            Stop
          </button>
        </div>
      )}

      {phase === "preview" && recorded && previewUrl && (
        <div className="space-y-3">
          <p className="font-mono">{formatTime(seconds)} recorded</p>
          <audio controls src={previewUrl} data-testid="preview-audio" />
          <div className="flex gap-2">
            <button onClick={() => void submit()} className="bg-blue-600 text-white rounded px-4 py-2">
              Upload
            </button>
            <button onClick={discard} className="border rounded px-4 py-2">
              Discard
            </button>
          </div>
        </div>
      )}

      {phase === "submitting" && <p>Uploading…</p>}
    </div>
  );
}
