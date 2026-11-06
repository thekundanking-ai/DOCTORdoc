import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";

const MOBILE_RE = /^\+?[0-9]{7,15}$/;

export default function PatientFormPage() {
  const { id } = useParams();
  const isEdit = id !== undefined;
  const navigate = useNavigate();

  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isEdit) return;
    api.patients
      .get(Number(id))
      .then((res) => {
        setFullName(res.data.full_name);
        setMobile(res.data.mobile);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load patient"))
      .finally(() => setLoading(false));
  }, [isEdit, id]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const name = fullName.trim();
    const mob = mobile.trim();
    if (!name || !MOBILE_RE.test(mob)) {
      setError("Enter a valid name and mobile (7–15 digits).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (isEdit) {
        await api.patients.update(Number(id), { full_name: name, mobile: mob });
      } else {
        await api.patients.create({ full_name: name, mobile: mob });
      }
      navigate("/patients");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="p-8">Loading…</div>;

  return (
    <form onSubmit={onSubmit} className="p-8 max-w-md mx-auto space-y-4">
      <h1 className="text-2xl font-bold">{isEdit ? "Edit patient" : "New patient"}</h1>
      <input
        value={fullName}
        onChange={(event) => setFullName(event.target.value)}
        placeholder="Full name"
        required
        className="w-full border rounded p-2"
      />
      <input
        value={mobile}
        onChange={(event) => setMobile(event.target.value)}
        placeholder="Mobile"
        required
        className="w-full border rounded p-2"
      />
      {error && <p className="text-red-600 text-sm">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="bg-blue-600 text-white rounded px-4 py-2">
          {busy ? "Saving…" : "Save"}
        </button>
        <Link to="/patients" className="border rounded px-4 py-2">
          Cancel
        </Link>
      </div>
    </form>
  );
}
