import { useState, type FormEvent } from "react";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const { error } = await signIn(email, password);
    setSubmitting(false);
    if (error) setError(error);
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Jananam Fertility Centre</h1>
        <p className="subtitle">Front Office — Appointment Portal</p>

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />

        {error && <p className="error-text">{error}</p>}

        <button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="hint">
          Accounts are created by an admin in the Supabase dashboard. Contact your
          administrator if you don't have a login yet.
        </p>
      </form>
    </div>
  );
}
