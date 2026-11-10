import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, ButtonLink } from "../components/ui/Button";
import { Card, Badge } from "../components/ui/Card";
import { EmptyState, ErrorState } from "../components/ui/States";
import { Modal } from "../components/ui/Modal";
import { BackIcon, PlusIcon } from "../components/ui/icons";
import { api, type Consultation, type Patient } from "../lib/api";
import TranscriptionPanel from "../components/TranscriptionPanel";

function statusTone(status: Consultation["status"]) {
  switch (status) {
    case "completed":
      return "success" as const;
    case "cancelled":
      return "neutral" as const;
    case "awaiting_transcription":
      return "warning" as const;
    default:
      return "info" as const;
  }
}

export default function PatientDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const navigate = useNavigate();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [consultations, setConsultations] = useState<Consultation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);

  const loadPatient = useCallback(async () => {
    const patientRes = await api.patients.get(id);
    setPatient(patientRes.data);
  }, [id]);

  const loadConsultations = useCallback(async () => {
    const consultationsRes = await api.consultations.list(id, { page_size: 50 });
    setConsultations(consultationsRes.data.items);
  }, [id]);

  const load = useCallback(async () => {
    setError(null);
    try {
      await Promise.all([loadPatient(), loadConsultations()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load patient");
    } finally {
      setLoading(false);
    }
  }, [loadPatient, loadConsultations]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmArchive() {
    if (!patient) return;
    try {
      await api.patients.archive(patient.id);
      navigate("/patients");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive patient");
    }
  }

  if (loading) return <div className="mx-auto max-w-3xl space-y-4">Loading…</div>;
  if (error || !patient) {
    return <ErrorState title="Patient not found" message={error ?? "This patient does not exist."} onRetry={() => void load()} />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <button onClick={() => navigate("/patients")} className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-sub hover:text-ink">
        <BackIcon width={17} height={17} /> All patients
      </button>

      <Card className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary-soft text-lg font-semibold text-primary">
              {patient.full_name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
            </div>
            <div>
              <h1 className="text-xl font-semibold text-ink">{patient.full_name}</h1>
              <p className="text-sm text-ink-sub">{patient.mobile}</p>
              <div className="mt-1.5">
                <Badge tone={patient.is_active ? "success" : "neutral"}>{patient.is_active ? "Active" : "Archived"}</Badge>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <ButtonLink to={`/patients/${patient.id}/edit`} variant="secondary" size="sm">Edit</ButtonLink>
            {patient.is_active && (
              <Button variant="secondary" size="sm" onClick={() => setArchiveOpen(true)}>Archive</Button>
            )}
          </div>
        </div>
      </Card>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">Consultations</h2>
          <ButtonLink to={`/patients/${patient.id}/consultations/new`} size="sm">
            <PlusIcon width={17} height={17} /> Start consultation
          </ButtonLink>
        </div>

        {consultations.length === 0 ? (
          <EmptyState
            icon={<PlusIcon width={22} height={22} />}
            title="No consultations yet"
            description="Start the first consultation for this patient."
            action={<ButtonLink to={`/patients/${patient.id}/consultations/new`} variant="secondary">Start consultation</ButtonLink>}
          />
        ) : (
          <div className="space-y-3">
            {consultations.map((consultation) => (
              <Card key={consultation.id} className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-ink">
                      {new Date(consultation.created_at).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </p>
                    <p className="text-[13px] text-ink-sub">
                      {consultation.audio ? "Audio recorded" : "No audio"}
                      <span className="mx-1.5 text-ink-faint">·</span>
                      {consultation.status.replace("_", " ")}
                    </p>
                  </div>
                  <Badge tone={statusTone(consultation.status)}>{consultation.status.replace("_", " ")}</Badge>
                </div>
                {(consultation.audio || consultation.status === "completed") && (
                  <TranscriptionPanel
                    consultationId={consultation.id}
                    hasAudio={!!consultation.audio}
                    patientId={patient.id}
                    onTerminal={() => void loadConsultations()}
                  />
                )}
              </Card>
            ))}
          </div>
        )}
      </section>

      <Modal
        open={archiveOpen}
        title="Archive patient?"
        description="The patient's consultation history is preserved."
        confirmLabel="Archive"
        tone="danger"
        onConfirm={() => void confirmArchive()}
        onCancel={() => setArchiveOpen(false)}
      />
    </div>
  );
}
