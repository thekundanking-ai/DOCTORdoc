import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/Button";
import { Field, Input } from "../components/ui/Input";
import { Card } from "../components/ui/Card";
import { Logo } from "../components/ui/Logo";
import { EyeIcon, EyeOffIcon } from "../components/ui/icons";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!email || !password) {
      setError("Enter both email and password.");
      return;
    }
    setBusy(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
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
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          <Field label="Email">
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="doctor@clinic.in"
              autoComplete="email"
            />
          </Field>
          <Field label="Password">
            <div className="relative">
              <Input
                type={show ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                className="pr-11"
              />
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1.5 text-ink-faint hover:text-ink-sub"
                aria-label={show ? "Hide password" : "Show password"}
              >
                {show ? <EyeOffIcon width={18} height={18} /> : <EyeIcon width={18} height={18} />}
              </button>
            </div>
          </Field>

          {error && <p className="rounded-control bg-red-50 px-3 py-2 text-sm text-danger">{error}</p>}

          <Button type="submit" fullWidth size="lg" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-6 text-center text-sm text-ink-sub">
          Need an account?{" "}
          <Link to="/register" className="font-medium text-primary hover:text-primary-hover">
            Create account
          </Link>
        </p>
      </Card>
    </div>
  );
}
