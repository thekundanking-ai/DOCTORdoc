import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Transcription, type TranscriptionStatus } from "../lib/api";

const STATUS_LABEL: Record<TranscriptionStatus, string> = {
  not_started: "Not started",
  submitting: "Submitting",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

// Terminal failures that cannot be retried by the user.
const PERMANENT_FAILURES = new Set([
  "PROVIDER_NOT_CONFIGURED",
  "PROCESSING_TIMEOUT",
  "AUDIO_MISSING",
  "UNSUPPORTED_AUDIO_FORMAT",
  "AUDIO_TOO_LARGE",
]);

type Props = {
  consultationId: number;
  hasAudio: boolean;
  patientId: number;
  onTerminal?: () => void;
};

export default function TranscriptionPanel({ consultationId, hasAudio, patientId, onTerminal }: Props) {
  const navigate = useNavigate();
  const [transcription, setTranscription] = useState<Transcription | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api.transcriptions.get(consultationId);
      setTranscription(res.data);
    } catch {
      setTranscription(null);
    } finally {
      setLoading(false);
    }
  }, [consultationId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activeStatus = transcription?.status;
  useEffect(() => {
    if (!activeStatus || !["submitting", "processing"].includes(activeStatus)) return;
    const interval = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(interval);
  }, [activeStatus, refresh]);

  const terminalNotified = useRef(false);
  useEffect(() => {
    if (!transcription?.status) return;
    const status = transcription.status;
    if (status === "completed" || status === "failed") {
      if (!terminalNotified.current) {
        terminalNotified.current = true;
        onTerminal?.();
      }
    } else {
      terminalNotified.current = false;
    }
  }, [transcription?.status, onTerminal]);

  async function confirmStart() {
    setCreating(true);
    setError(null);
    try {
      const res = await api.transcriptions.start(consultationId);
      setTranscription(res.data);
      setConfirmOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start transcription");
    } finally {
      setCreating(false);
    }
  }

  async function handleRetry() {
    setCreating(true);
    setError(null);
    try {
      const res = await api.transcriptions.retry(consultationId);
      setTranscription(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry");
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <p className="text-sm text-gray-500">Loading transcription…</p>;

  const isActive = transcription && ["submitting", "processing"].includes(transcription.status);

  return (
    <div className="border rounded p-3 space-y-2">
      <h3 className="font-semibold text-sm">Transcription</h3>

      {transcription ? (
        <>
          <div className="flex items-center gap-2 text-sm">
            <span className="rounded bg-gray-100 px-2 py-0.5">
              {STATUS_LABEL[transcription.status as TranscriptionStatus]}
            </span>
            {isActive && <span className="text-gray-500">Working…</span>}
          </div>

          {transcription.status === "completed" && (
            <>
              <div className="text-xs text-gray-500 space-y-0.5">
                <p>Provider: {transcription.provider} · model {transcription.provider_model}</p>
                {transcription.detected_language && <p>Detected language: {transcription.detected_language}</p>}
                {transcription.completed_at && <p>Completed: {new Date(transcription.completed_at).toLocaleString()}</p>}
              </div>
              <p className="text-sm whitespace-pre-wrap rounded bg-gray-50 p-2">
                {transcription.transcript_text}
              </p>
              <p className="text-xs text-amber-700">
                AI transcription may contain errors. The doctor must review the transcript before using it for medical
                documentation.
              </p>
              <button
                onClick={() => navigate(`/patients/${patientId}/consultations/${consultationId}/report`)}
                className="rounded bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-hover"
              >
                Generate Consultation Report
              </button>
            </>
          )}

          {transcription.status === "failed" && (
            <div className="text-sm space-y-2">
              <p className="text-red-600">{transcription.error_message || "Transcription failed."}</p>
              {transcription.error_code === "PROCESSING_TIMEOUT" && (
                <p className="text-xs text-gray-500">
                  The provider never finished in time. Start a fresh transcription for this consultation.
                </p>
              )}
              {transcription.provider_status && (
                <p className="text-xs text-gray-400">Last provider status: {transcription.provider_status}</p>
              )}
              {transcription.error_code && !PERMANENT_FAILURES.has(transcription.error_code) && (
                <button onClick={() => void handleRetry()} disabled={creating} className="border rounded px-3 py-1">
                  {creating ? "Retrying…" : "Retry"}
                </button>
              )}
            </div>
          )}
        </>
      ) : (
        <>
          {!hasAudio && <p className="text-sm text-gray-500">Upload an audio recording first.</p>}
          {hasAudio && !confirmOpen && (
            <button onClick={() => setConfirmOpen(true)} className="bg-blue-600 text-white rounded px-3 py-1 text-sm">
              Transcribe audio
            </button>
          )}
          {hasAudio && confirmOpen && (
            <div className="text-sm space-y-2">
              <p>The audio recording will be sent to Gnani AI for speech-to-text transcription.</p>
              <div className="flex gap-2">
                <button onClick={() => void confirmStart()} disabled={creating} className="bg-blue-600 text-white rounded px-3 py-1">
                  {creating ? "Submitting…" : "Confirm and submit"}
                </button>
                <button onClick={() => setConfirmOpen(false)} className="border rounded px-3 py-1">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {error && <p className="text-red-600 text-sm">{error}</p>}
    </div>
  );
}
