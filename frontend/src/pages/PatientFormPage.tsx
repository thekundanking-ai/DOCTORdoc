import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Field, Input } from "../components/ui/Input";
import { Skeleton } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { api } from "../lib/api";

const MOBILE_RE = /^\+?[0-9]{7,15}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export default function PatientFormPage() {
  const { id } = useParams();
  const isEdit = id !== undefined;
  const navigate = useNavigate();
  const { push } = useToast();

  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(isEdit);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ name?: string; mobile?: string; email?: string; server?: string }>({});

  useEffect(() => {
    if (!isEdit) return;
    api.patients
      .get(Number(id))
      .then((res) => {
        setName(res.data.full_name);
        setMobile(res.data.mobile);
        setEmail(res.data.email ?? "");
      })
      .catch((err) => setErrors({ server: err instanceof Error ? err.message : "Failed to load patient" }))
      .finally(() => setLoading(false));
  }, [isEdit, id]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    if (!name.trim() || name.trim().length < 2) next.name = "Enter the patient's full name.";
    const mob = mobile.replace(/\s+/g, "");
    if (!MOBILE_RE.test(mob)) next.mobile = "Enter a valid mobile number (7–15 digits).";
    const em = (email || "").trim();
    if (em && !EMAIL_RE.test(em)) next.email = "Enter a valid email address (or leave blank).";
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setBusy(true);
    try {
      if (isEdit) {
        await api.patients.update(Number(id), { full_name: name.trim(), mobile: mob, email: em || null });
        push("Patient updated");
        navigate(`/patients/${id}`);
      } else {
        const patient = await api.patients.create({ full_name: name.trim(), mobile: mob, email: em || null });
        push("Patient added");
        navigate(`/patients/${patient.data.id}`);
      }
    } catch (err) {
      setErrors({ server: err instanceof Error ? err.message : "Save failed" });
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="mx-auto max-w-xl"><Skeleton className="h-40" /></div>;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{isEdit ? "Edit patient" : "Add patient"}</h1>
        <p className="mt-1 text-sm text-ink-sub">{isEdit ? "Update patient details." : "Register a new patient."}</p>
      </div>

      <Card className="p-6">
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          {errors.server && <p className="rounded-control bg-red-50 px-3 py-2 text-sm text-danger">{errors.server}</p>}
          <Field label="Full name" error={errors.name}>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Ramesh Iyer" autoFocus />
          </Field>
          <Field label="Mobile number" error={errors.mobile} hint="7–15 digits, optional + prefix">
            <Input value={mobile} onChange={(e) => setMobile(e.target.value)} placeholder="+91 98450 12345" inputMode="tel" />
          </Field>
          <Field label="Email (optional)" error={errors.email} hint="Used to send the report PDF">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="patient@example.com" inputMode="email" />
          </Field>
          <div className="flex gap-2 pt-1">
            <Button type="submit" disabled={busy}>{busy ? "SavingÃ¢â‚¬Â¦" : isEdit ? "Save changes" : "Add patient"}</Button>
            <Button type="button" variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}


