import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { BackIcon } from "../components/ui/icons";
import { api, type Patient } from "../lib/api";
import Recorder from "../components/Recorder";

function makeUploadId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `upload-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ConsultationRecorderPage() {
  const patientId = Number(useParams<{ id: string }>().id);
  const navigate = useNavigate();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [consented, setConsented] = useState(false);
  const [starting, setStarting] = useState(false);
  const [consultationId, setConsultationId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.patients
      .get(patientId)
      .then((res) => setPatient(res.data))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load patient"));
  }, [patientId]);

  async function createConsultation() {
    setStarting(true);
    setError(null);
    try {
      const res = await api.consultations.create(patientId);
      setConsultationId(res.data.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start consultation");
    } finally {
      setStarting(false);
    }
  }

  async function handleUpload(blob: Blob, durationSeconds: number) {
    if (consultationId === null) return;
    await api.consultations.uploadAudio(consultationId, blob, makeUploadId(), durationSeconds);
    navigate(`/patients/${patientId}`);
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <button onClick={() => navigate(`/patients/${patientId}`)} className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-sub hover:text-ink">
        <BackIcon width={17} height={17} /> {patient?.full_name ?? "Back to patient"}
      </button>

      <Card className="p-6">
        <h1 className="text-lg font-semibold text-ink">New consultation</h1>
        {patient && <p className="mt-0.5 text-sm text-ink-sub">{patient.full_name} · {patient.mobile}</p>}

        {error && <p className="mt-4 rounded-control bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}

        {consultationId === null ? (
          <div className="mt-6 space-y-4">
            <label className="flex items-start gap-2.5 text-sm text-ink">
              <input
                type="checkbox"
                checked={consented}
                onChange={(e) => setConsented(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-line text-primary focus:ring-primary"
              />
              <span>I confirm the patient has consented to being recorded for this consultation.</span>
            </label>
            <Button fullWidth disabled={!consented || starting} onClick={() => void createConsultation()}>
              {starting ? "Starting…" : "Continue"}
            </Button>
          </div>
        ) : (
          <div className="mt-6">
            <Recorder onSubmit={handleUpload} onBack={() => navigate(`/patients/${patientId}`)} />
          </div>
        )}
      </Card>
    </div>
  );
}
