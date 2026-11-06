import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Patient } from "../lib/api";

export default function PatientDetailPage() {
  const id = Number(useParams<{ id: string }>().id);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.patients
      .get(id)
      .then((res) => setPatient(res.data))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load patient"))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleArchive() {
    if (!patient) return;
    try {
      await api.patients.archive(patient.id);
      const res = await api.patients.get(patient.id);
      setPatient(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive patient");
    }
  }

  if (loading) return <div className="p-8">Loading…</div>;

  return (
    <div className="p-8 max-w-md mx-auto space-y-4">
      {error ? (
        <p className="text-red-600">{error}</p>
      ) : patient ? (
        <>
          <h1 className="text-2xl font-bold">{patient.full_name}</h1>
          <p>Mobile: {patient.mobile}</p>
          <p>Status: {patient.is_active ? "Active" : "Archived"}</p>
          <p>Created by user #{patient.created_by}</p>
          {!patient.is_active && (
            <button disabled className="border rounded px-3 py-1 opacity-50">
              Archived
            </button>
          )}
          <div className="flex gap-2">
            <Link to={`/patients/${patient.id}/edit`} className="bg-blue-600 text-white rounded px-4 py-2">
              Edit
            </Link>
            {patient.is_active && (
              <button onClick={() => void handleArchive()} className="bg-red-600 text-white rounded px-4 py-2">
                Archive
              </button>
            )}
            <Link to="/patients" className="border rounded px-4 py-2">
              Back
            </Link>
          </div>
        </>
      ) : null}
    </div>
  );
}
