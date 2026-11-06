import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Patient } from "../lib/api";

const PAGE_SIZE = 10;

export default function PatientsPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.patients.list({
        q: submittedQuery || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setPatients(res.data.items);
      setTotal(res.data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load patients");
    } finally {
      setLoading(false);
    }
  }, [submittedQuery, page]);

  useEffect(() => {
    void load();
  }, [load]);

  function handleSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setSubmittedQuery(query.trim());
  }

  async function handleArchive(id: number) {
    try {
      await api.patients.archive(id);
      void load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive patient");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Patients</h1>
        <Link to="/patients/new" className="bg-blue-600 text-white rounded px-4 py-2">
          New patient
        </Link>
      </div>

      <form onSubmit={handleSearch} className="mt-4 flex gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name or mobile"
          className="flex-1 border rounded p-2"
        />
        <button type="submit" className="bg-gray-800 text-white rounded px-4 py-2">
          Search
        </button>
      </form>

      {loading && <p className="mt-6">Loading…</p>}
      {!loading && error && <p className="mt-6 text-red-600">{error}</p>}
      {!loading && !error && patients.length === 0 && (
        <p className="mt-6">No patients found.</p>
      )}
      {!loading && !error && patients.length > 0 && (
        <table className="mt-6 w-full text-left border-collapse">
          <thead>
            <tr className="border-b">
              <th className="py-2">Name</th>
              <th>Mobile</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {patients.map((patient) => (
              <tr key={patient.id} className="border-b">
                <td className="py-2">{patient.full_name}</td>
                <td>{patient.mobile}</td>
                <td>{patient.is_active ? "Active" : "Archived"}</td>
                <td className="flex gap-2">
                  <Link to={`/patients/${patient.id}`} className="text-blue-600">
                    View
                  </Link>
                  <Link to={`/patients/${patient.id}/edit`} className="text-blue-600">
                    Edit
                  </Link>
                  {patient.is_active && (
                    <button onClick={() => void handleArchive(patient.id)} className="text-red-600">
                      Archive
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="mt-4 flex items-center justify-between">
        <button
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
          className="border rounded px-3 py-1 disabled:opacity-40"
        >
          Previous
        </button>
        <span>
          Page {page} of {totalPages}
        </span>
        <button
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages}
          className="border rounded px-3 py-1 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
