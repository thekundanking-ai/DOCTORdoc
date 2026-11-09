import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ButtonLink } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/States";
import { Skeleton } from "../components/ui/Skeleton";
import { PlusIcon, SearchIcon, ChevronRightIcon } from "../components/ui/icons";
import { api, type Patient } from "../lib/api";

export default function Dashboard() {
  const { user } = useAuth();
  const [recent, setRecent] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.patients
      .list({ page_size: 5 })
      .then((res) => setRecent(res.data.items))
      .catch(() => setRecent([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <p className="text-sm text-ink-sub">Welcome back,</p>
        <h1 className="mt-0.5 text-2xl font-semibold text-ink md:text-3xl">
          {user?.full_name || "Doctor"}
        </h1>
        <p className="mt-1 text-sm text-ink-sub">Start a consultation or manage your patients.</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="p-6">
          <h2 className="text-base font-semibold text-ink">Start a consultation</h2>
          <p className="mt-1 text-sm text-ink-sub">Record and transcribe a patient visit.</p>
          <ButtonLink to="/patients" className="mt-4">
            <SearchIcon width={18} height={18} /> Choose a patient
          </ButtonLink>
        </Card>
        <Card className="p-6">
          <h2 className="text-base font-semibold text-ink">Add a patient</h2>
          <p className="mt-1 text-sm text-ink-sub">Register a new patient in a few seconds.</p>
          <ButtonLink to="/patients/new" variant="secondary" className="mt-4">
            <PlusIcon width={18} height={18} /> Add patient
          </ButtonLink>
        </Card>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">Recent patients</h2>
          <Link to="/patients" className="text-sm font-medium text-primary hover:text-primary-hover">
            View all patients
          </Link>
        </div>

        {loading ? (
          <div className="space-y-2.5">
            {[0, 1, 2].map((i) => (
              <Card key={i} className="p-4">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="mt-2 h-3 w-1/4" />
              </Card>
            ))}
          </div>
        ) : recent.length === 0 ? (
          <EmptyState
            icon={<SearchIcon width={22} height={22} />}
            title="No patients yet"
            description="Add your first patient to get started."
            action={<ButtonLink to="/patients/new" variant="secondary"><PlusIcon width={18} height={18} /> Add patient</ButtonLink>}
          />
        ) : (
          <div className="space-y-2.5">
            {recent.map((patient) => (
              <Link key={patient.id} to={`/patients/${patient.id}`} className="block">
                <Card className="flex items-center justify-between p-4 transition-colors hover:border-primary/40">
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
                      {patient.full_name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-ink">{patient.full_name}</p>
                      <p className="text-[13px] text-ink-sub">{patient.mobile}</p>
                    </div>
                  </div>
                  <ChevronRightIcon className="text-ink-faint" />
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
