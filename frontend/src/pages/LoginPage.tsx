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
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-tinta px-4 text-papel">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 27px, currentColor 28px), repeating-linear-gradient(90deg, transparent, transparent 27px, currentColor 28px)",
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-1/3 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-sello/10 blur-3xl"
      />

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm space-y-6 rounded-xl border border-white/10 bg-tinta-2/80 p-8 shadow-2xl backdrop-blur"
      >
        <div className="space-y-1 text-center">
          <p className="text-[0.6875rem] tracking-[0.24em] text-papel/50 uppercase">Sala de vigilancia jurídica</p>
          <h1 className="font-display text-3xl font-semibold tracking-tight">IURISYNC</h1>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="login-api-key" className="text-xs font-medium text-papel/70">
            Clave de acceso
          </label>
          <input
            id="login-api-key"
            type="password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            placeholder="API key"
            required
            className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
          />
        </div>

        {error && (
          <p className="rounded-md border border-rojo/40 bg-rojo/10 px-3 py-2 text-sm text-rojo-bg">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-sello px-3 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-sello-ink disabled:opacity-60"
        >
          {submitting ? "Verificando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
