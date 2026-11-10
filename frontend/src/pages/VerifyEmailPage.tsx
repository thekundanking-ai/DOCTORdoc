import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Field, Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { Logo } from "../components/ui/Logo";

type VerifyState = {
  email?: string;
  devToken?: string;
};

const EXPIRED_MESSAGE = "This verification link has expired. Please request a new one.";
const INVALID_MESSAGE = "Invalid verification token. Check the token and try again.";

export default function VerifyEmailPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state ?? {}) as VerifyState;
  const hasDevToken = Boolean(state.devToken);
  const [token, setToken] = useState(state.devToken ?? "");
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const trimmed = token.trim();
    if (!trimmed) {
      setError("Enter your verification token.");
      return;
    }
    setBusy(true);
    try {
      await api.verifyEmail(trimmed);
      setSuccess(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      setError(/has expired/.test(message.toLowerCase()) ? EXPIRED_MESSAGE : INVALID_MESSAGE);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <Card className="w-full max-w-md p-8">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>

        {success ? (
          <>
            <p className="rounded-control bg-green-50 px-3 py-2 text-sm text-green-700">Email verified</p>
            <p className="mt-2 text-sm text-ink-sub">Your account is active. You can now sign in.</p>
            <Button onClick={() => navigate("/login")} fullWidth size="lg" className="mt-6">
              Sign In
            </Button>
          </>
        ) : hasDevToken ? (
          <>
            <p className="mb-5 text-sm text-ink-sub">
              Your account was created. Confirm the verification token below to activate it.
            </p>
            <form onSubmit={onSubmit} className="space-y-5" noValidate>
              <Field label="Verification token">
                <Input
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste your verification token"
                  autoComplete="off"
                />
              </Field>
              {error && <p className="rounded-control bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}
              <Button type="submit" fullWidth size="lg" disabled={busy}>
                {busy ? "Verifying…" : "Verify email"}
              </Button>
            </form>
          </>
        ) : (
          <>
            <p className="text-sm text-ink-sub">Check your email and use the verification link.</p>
            <p className="mt-2 text-sm text-ink-sub">Once verified, sign in to continue.</p>
            <Button variant="secondary" onClick={() => navigate("/login")} fullWidth size="lg" className="mt-6">
              Back to sign in
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
