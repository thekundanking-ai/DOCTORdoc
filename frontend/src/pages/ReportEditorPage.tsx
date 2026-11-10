import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, ButtonLink } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState, ErrorState } from "../components/ui/States";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { BackIcon } from "../components/ui/icons";
import { api, type Delivery, type Report, type ReportStructured } from "../lib/api";

function asLines(value: string[] | null | undefined): string {
  return (value || []).join("\n");
}

function fromLines(text: string): string[] {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

type FieldProps = { label: string; value: string; onChange: (v: string) => void; multiline?: boolean; hint?: string };

function EditField({ label, value, onChange, multiline }: FieldProps) {
  return (
    <label className="block">
      <span className="mb-1 block text-[13px] font-medium text-ink">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          className="w-full rounded-control border border-line bg-white px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-11 w-full rounded-control border border-line bg-white px-3.5 text-sm text-ink outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
        />
      )}
    </label>
  );
}

const SECTIONS: { key: keyof ReportStructured; label: string; multiline?: boolean }[] = [
  { key: "chief_complaint", label: "Chief complaint" },
  { key: "symptoms", label: "Symptoms (one per line)", multiline: true },
  { key: "medical_history", label: "Medical history", multiline: true },
  { key: "clinical_observations", label: "Clinical observations (one per line)", multiline: true },
  { key: "diagnosis", label: "Diagnosis" },
  { key: "investigations", label: "Investigations (one per line)", multiline: true },
  { key: "treatment_and_advice", label: "Treatment and advice", multiline: true },
  { key: "follow_up", label: "Follow-up", multiline: true },
  { key: "unclear_or_missing", label: "Unclear / missing information (one per line)", multiline: true },
];

export default function ReportEditorPage() {
  const { id: patientId, cid } = useParams<{ id: string; cid: string }>();
  const consultationId = Number(cid);
  const navigate = useNavigate();
  const { push } = useToast();

  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<ReportStructured>({});
  const [busy, setBusy] = useState(false);
  const [regenOpen, setRegenOpen] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [sentOnce, setSentOnce] = useState(false);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.reports.get(consultationId);
      setReport(res.data);
      setDraft(res.data.structured_report ?? {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  }, [consultationId]);

  const loadDeliveries = useCallback(async () => {
    try {
      const res = await api.reports.deliveries(consultationId);
      setDeliveries(Array.isArray(res.data) ? res.data : []);
    } catch {
      setDeliveries([]);
    }
  }, [consultationId]);

  useEffect(() => {
    void load();
    void loadDeliveries();
  }, [load, loadDeliveries]);

  function setField(key: keyof ReportStructured, value: string | string[]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function setMedField(index: number, field: keyof NonNullable<ReportStructured["medications"]>[number], value: string) {
    setDraft((prev) => {
      const medications = [...(prev.medications || [])];
      medications[index] = { ...medications[index], [field]: value };
      return { ...prev, medications };
    });
  }

  function removeMed(index: number) {
    setDraft((prev) => {
      const medications = [...(prev.medications || [])];
      medications.splice(index, 1);
      return { ...prev, medications };
    });
  }

  function addMed() {
    setDraft((prev) => ({
      ...prev,
      medications: [...(prev.medications || []), { name: null, dosage: null, frequency: null, duration: null }],
    }));
  }

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.reports.generate(consultationId);
      setReport(res.data);
      setDraft(res.data.structured_report ?? {});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.reports.update(consultationId, draft);
      setReport(res.data);
      setDraft(res.data.structured_report ?? {});
      push("Draft saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.reports.approve(consultationId);
      setReport(res.data);
      setApproveOpen(false);
      push("Report approved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf() {
    setError(null);
    try {
      const blob = await api.reports.downloadPdf(consultationId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report-${consultationId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF download failed");
    }
  }

  async function deliver() {
    setSending(true);
    setError(null);
    try {
      const res = await api.reports.deliver(consultationId);
      if (res.data.status === "sent") {
        setSentOnce(true);
        push("Report sent to patient");
      } else {
        push(`Delivery ${res.data.status}`);
      }
      await loadDeliveries();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Delivery failed";
      setError(msg);
      push(msg);
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const current = report?.status === "approved" ? report.structured_report : draft;
  const warnings = current?.unclear_or_missing || [];
  const approved = report?.status === "approved";
  const deliveryDone = sentOnce || deliveries.some((d) => d.status === "sent");
  const generating = report?.status === "generating";
  const failed = report?.status === "failed";

  const backTo = `/patients/${patientId}`;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <button onClick={() => navigate(backTo)} className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-sub hover:text-ink">
        <BackIcon width={17} height={17} /> Back to patient
      </button>

      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Consultation report</h1>
          <p className="mt-1 text-sm text-ink-sub">
            {report ? `Status: ${report.status.replace("_", " ")}` : "No report yet"}
          </p>
        </div>
        {report && !approved && (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setRegenOpen(true)} disabled={busy || generating}>
              Regenerate
            </Button>
            <Button size="sm" onClick={() => setApproveOpen(true)} disabled={busy || generating || failed || !report?.structured_report}>
              Approve
            </Button>
          </div>
        )}
      </div>

      {error && <ErrorState message={error} onRetry={() => setError(null)} />}

      {!report && !loading && (
        <EmptyState
          title="No report generated"
          description="Generate a structured report from the completed transcript."
          action={<Button onClick={() => void generate()} disabled={busy}>{busy ? "Generatingâ€¦" : "Generate Consultation Report"}</Button>}
        />
      )}

      {generating && (
        <Card className="p-6">
          <div className="flex items-center gap-3">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary" />
            <span className="text-sm text-primary">Generating reportâ€¦</span>
          </div>
        </Card>
      )}

      {failed && (
        <ErrorState title="Report generation failed" message={report?.error_message || "Could not generate the report."} onRetry={() => void generate()} />
      )}

      {report && current && !generating && (
        <>
          {!approved && (warnings.length > 0 || !current.diagnosis) && (
            <Card className="border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-warning">Review required</p>
              <ul className="mt-1 list-inside list-disc text-sm text-amber-800">
                {!current.diagnosis && <li>No diagnosis recorded â€” confirm the diagnosis before approving.</li>}
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
                {current.medications?.length ? (
                  <li>Confirm all medication details before approving.</li>
                ) : null}
              </ul>
              <p className="mt-2 text-xs text-amber-700">
                AI transcription and report generation may contain errors. Review before using for medical documentation.
              </p>
            </Card>
          )}

          <Card className="space-y-5 p-6">
            <div className="rounded-control bg-slate-50 p-4">
              <h2 className="text-sm font-semibold text-ink">Patient information</h2>
              <div className="mt-2 grid gap-2 text-sm text-ink-sub sm:grid-cols-3">
                <span>Name: {current.patient_information?.name ?? "â€”"}</span>
                <span>Mobile: {current.patient_information?.mobile ?? "â€”"}</span>
                <span>Date: {current.patient_information?.consultation_date ?? "â€”"}</span>
              </div>
            </div>

            {approved ? (
              <div className="space-y-4">
                {SECTIONS.map((section) => (
                  <div key={section.key}>
                    <h3 className="mb-1 text-[13px] font-medium text-ink">{section.label}</h3>
                    {Array.isArray(current[section.key]) ? (
                      <p className="whitespace-pre-wrap text-sm text-ink">
                        {(current[section.key] as string[])?.join("\n") || "â€”"}
                      </p>
                    ) : (
                      <p className="whitespace-pre-wrap text-sm text-ink">
                        {(current[section.key] as string) || "â€”"}
                      </p>
                    )}
                  </div>
                ))}
                <div>
                  <h3 className="mb-1 text-[13px] font-medium text-ink">Medications</h3>
                  {!current.medications?.length ? (
                    <p className="text-sm text-ink">â€”</p>
                  ) : (
                    current.medications.map((m, i) => (
                      <p key={i} className="text-sm text-ink">
                        {m.name ?? "â€”"} Â· {m.dosage ?? "â€”"} Â· {m.frequency ?? "â€”"} Â· {m.duration ?? "â€”"}
                      </p>
                    ))
                  )}
                </div>
              </div>
            ) : (
              <>
                {SECTIONS.map((section) => (
                  <EditField
                    key={section.key}
                    label={section.label}
                    multiline={section.multiline}
                    value={Array.isArray(current[section.key]) ? asLines(current[section.key] as string[]) : ((current[section.key] as string) ?? "")}
                    onChange={(v) =>
                      setField(section.key, section.multiline ? fromLines(v) : v)
                    }
                  />
                ))}

                <div>
                  <h3 className="mb-2 text-[13px] font-medium text-ink">Medications</h3>
                  <div className="space-y-2">
                    {(current.medications || []).map((med, i) => (
                      <div key={i} className="grid gap-2 sm:grid-cols-4">
                        <input value={med.name ?? ""} onChange={(e) => setMedField(i, "name", e.target.value)} placeholder="Name" className="h-10 rounded-control border border-line bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" />
                        <input value={med.dosage ?? ""} onChange={(e) => setMedField(i, "dosage", e.target.value)} placeholder="Dosage" className="h-10 rounded-control border border-line bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" />
                        <input value={med.frequency ?? ""} onChange={(e) => setMedField(i, "frequency", e.target.value)} placeholder="Frequency" className="h-10 rounded-control border border-line bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" />
                        <div className="flex gap-1">
                          <input value={med.duration ?? ""} onChange={(e) => setMedField(i, "duration", e.target.value)} placeholder="Duration" className="h-10 flex-1 rounded-control border border-line bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20" />
                          <button onClick={() => removeMed(i)} className="rounded-control px-2 text-sm text-danger hover:bg-red-50" aria-label={`Remove medication ${i + 1}`}>Ã—</button>
                        </div>
                      </div>
                    ))}
                    <Button type="button" variant="secondary" size="sm" onClick={addMed}>
                      + Add medication
                    </Button>
                  </div>
                </div>

                <div className="flex gap-2 border-t border-line pt-4">
                  <Button onClick={() => void saveDraft()} disabled={busy}>{busy ? "Savingâ€¦" : "Save Draft"}</Button>
                  <ButtonLink to={backTo} variant="secondary">Back</ButtonLink>
                </div>
              </>
            )}
          </Card>

          {approved && (
            <div className="space-y-3 border-t border-line pt-4">
              <p className="text-sm text-success">
                Approved by {report.approved_by ? `user #${report.approved_by}` : "doctor"} on{" "}
                {report.approved_at ? new Date(report.approved_at).toLocaleString() : "â€”"}
              </p>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => void downloadPdf()}>
                  Download PDF
                </Button>
                <Button size="sm" onClick={() => void deliver()} disabled={sending || deliveryDone}>
                  {sending ? "Sendingâ€¦" : deliveryDone ? "Report sent" : "Send Report"}
                </Button>
              </div>
              <div className="border-t border-line pt-3">
                <h3 className="mb-2 text-[13px] font-medium text-ink">Delivery history</h3>
                {deliveries.length === 0 ? (
                  <p className="text-sm text-ink-sub">No delivery attempts yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {deliveries.map((d) => (
                      <li key={d.id} className="rounded-control border border-line p-3 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className={d.status === "sent" ? "font-medium text-success" : d.status === "failed" ? "font-medium text-danger" : "font-medium text-ink"}>
                            {d.status === "sent" ? "Sent via SMTP" : d.status === "failed" ? "Failed" : "Pending"}
                          </span>
                          <span className="text-xs text-ink-sub">{d.created_at ? new Date(d.created_at).toLocaleString() : "â€”"}</span>
                        </div>
                        {d.recipient && <p className="mt-1 text-xs text-ink-sub">Recipient: {d.recipient}</p>}
                        {d.status === "sent" ? (
                          <p className="mt-1 text-xs text-ink-sub">Accepted by the mail server (SMTP â€” not inbox-confirmed).</p>
                        ) : d.error_message ? (
                          <p className="mt-1 text-xs text-danger">{d.error_message}</p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </>
      )}

      <Modal
        open={regenOpen}
        title="Regenerate report?"
        description="The current draft will be replaced with a new AI-generated version. Any edits you made will be lost."
        confirmLabel="Regenerate"
        onConfirm={() => {
          setRegenOpen(false);
          void generate();
        }}
        onCancel={() => setRegenOpen(false)}
      />

      <Modal
        open={approveOpen}
        title="Approve report?"
        description="Approving finalizes the report and makes it read-only. Confirm you have reviewed it."
        confirmLabel="Approve"
        onConfirm={() => void approve()}
        onCancel={() => setApproveOpen(false)}
      />
    </div>
  );
}

