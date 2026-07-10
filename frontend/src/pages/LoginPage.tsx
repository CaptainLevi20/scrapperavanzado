import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { fetchSourceFamilies } from "../api/sourceFamilies";
import { clearStoredApiKey, setStoredApiKey } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setStoredApiKey(key);
    try {
      await fetchSourceFamilies();
      login(key);
      navigate("/", { replace: true });
    } catch {
      clearStoredApiKey();
      setError("API key inválida");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-lg border p-6">
        <h1 className="text-xl font-semibold">IURISYNC — Ingresar</h1>
        <input
          type="password"
          value={key}
          onChange={(event) => setKey(event.target.value)}
          placeholder="API key"
          className="w-full rounded border px-3 py-2"
          required
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={submitting} className="w-full rounded bg-slate-900 px-3 py-2 text-white">
          {submitting ? "Verificando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
