import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function RegisterPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login: setSession } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden");
      return;
    }
    setSubmitting(true);
    try {
      const { token, username: registeredUsername, is_admin } = await register(username, password, inviteCode);
      setSession(token, registeredUsername, is_admin);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo completar el registro");
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

      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-sm space-y-6 rounded-xl border border-white/10 bg-tinta-2/80 p-8 shadow-2xl backdrop-blur"
      >
        <div className="space-y-1 text-center">
          <p className="text-[0.6875rem] tracking-[0.24em] text-papel/50 uppercase">Sala de vigilancia jurídica</p>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Crear cuenta</h1>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label htmlFor="register-username" className="text-xs font-medium text-papel/70">
              Usuario
            </label>
            <input
              id="register-username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Usuario"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="register-password" className="text-xs font-medium text-papel/70">
              Contraseña
            </label>
            <input
              id="register-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Mínimo 8 caracteres"
              required
              minLength={8}
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="register-confirm-password" className="text-xs font-medium text-papel/70">
              Confirmar contraseña
            </label>
            <input
              id="register-confirm-password"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Repite la contraseña"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="register-invite-code" className="text-xs font-medium text-papel/70">
              Código de invitación
            </label>
            <input
              id="register-invite-code"
              type="text"
              value={inviteCode}
              onChange={(event) => setInviteCode(event.target.value)}
              placeholder="Código de invitación"
              required
              className="w-full rounded-md border border-white/15 bg-tinta px-3 py-2.5 text-sm text-papel placeholder:text-papel/30 outline-none focus-visible:border-sello focus-visible:ring-[3px] focus-visible:ring-sello/30"
            />
          </div>
        </div>

        {error && (
          <p className="rounded-md border border-rojo/40 bg-rojo/10 px-3 py-2 text-sm text-rojo-bg">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-sello px-3 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-sello-ink disabled:opacity-60"
        >
          {submitting ? "Creando cuenta…" : "Crear cuenta"}
        </button>

        <p className="text-center text-xs text-papel/50">
          ¿Ya tienes cuenta?{" "}
          <Link to="/login" className="font-medium text-sello hover:underline">
            Entrar
          </Link>
        </p>
      </form>
    </div>
  );
}
