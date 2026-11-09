import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button, ButtonLink } from "../components/ui/Button";
import { Card, Badge } from "../components/ui/Card";
import { EmptyState, ErrorState } from "../components/ui/States";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { PlusIcon, SearchIcon, ChevronRightIcon } from "../components/ui/icons";
import { api, type Patient } from "../lib/api";

const PAGE_SIZE = 10;

export default function PatientsPage() {
  const { push } = useToast();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveId, setArchiveId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.patients.list({ q: submittedQuery || undefined, page, page_size: PAGE_SIZE });
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

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setSubmittedQuery(query.trim());
  }

  async function confirmArchive() {
    if (archiveId === null) return;
    try {
      await api.patients.archive(archiveId);
      push("Patient archived", "info");
      setArchiveId(null);
      void load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive patient");
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasQuery = submittedQuery.length > 0;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Patients</h1>
          <p className="mt-1 text-sm text-ink-sub">Search, add, and open patient records.</p>
        </div>
        <ButtonLink to="/patients/new">
          <PlusIcon width={18} height={18} /> Add patient
        </ButtonLink>
      </div>

      <form onSubmit={onSearch} className="relative">
        <SearchIcon width={18} height={18} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name or mobile number"
          className="h-11 w-full rounded-control border border-line bg-white pl-10 pr-4 text-sm text-ink placeholder:text-ink-faint outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
          aria-label="Search patients"
        />
      </form>

      {error && <ErrorState message={error} onRetry={() => void load()} />}

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="p-4">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="mt-2 h-3 w-1/4" />
            </Card>
          ))}
        </div>
      ) : patients.length === 0 ? (
        <EmptyState
          icon={<SearchIcon width={22} height={22} />}
          title={hasQuery ? "No patients found" : "No patients yet"}
          description={hasQuery ? "Try a different name or mobile number." : "Add your first patient to get started."}
          action={<ButtonLink to="/patients/new" variant="secondary"><PlusIcon width={18} height={18} /> Add patient</ButtonLink>}
        />
      ) : (
        <div className="space-y-2.5">
          {patients.map((patient) => (
            <Card key={patient.id} className="p-4">
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
                  {patient.full_name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink">{patient.full_name}</p>
                  <p className="text-[13px] text-ink-sub">{patient.mobile}</p>
                </div>
                <Badge tone={patient.is_active ? "success" : "neutral"}>{patient.is_active ? "Active" : "Archived"}</Badge>
                <div className="hidden items-center gap-2 sm:flex">
                  {patient.is_active && (
                    <Button variant="secondary" size="sm" onClick={() => setArchiveId(patient.id)}>
                      Archive
                    </Button>
                  )}
                  <ButtonLink to={`/patients/${patient.id}`} variant="secondary" size="sm">
                    Open <ChevronRightIcon width={15} height={15} />
                  </ButtonLink>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-2 border-t border-line pt-3 sm:hidden">
                <ButtonLink to={`/patients/${patient.id}`} variant="secondary" size="sm" className="flex-1">
                  Open
                </ButtonLink>
                {patient.is_active && (
                  <Button variant="secondary" size="sm" className="flex-1" onClick={() => setArchiveId(patient.id)}>
                    Archive
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {!loading && !error && patients.length > 0 && (
        <div className="flex items-center justify-between">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Previous
          </Button>
          <span className="text-sm text-ink-sub">
            Page {page} of {totalPages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
            Next
          </Button>
        </div>
      )}

      <Modal
        open={archiveId !== null}
        title="Archive patient?"
        description="The patient's history is preserved, but they will not appear in active search."
        confirmLabel="Archive"
        tone="danger"
        onConfirm={confirmArchive}
        onCancel={() => setArchiveId(null)}
      />
    </div>
  );
}
