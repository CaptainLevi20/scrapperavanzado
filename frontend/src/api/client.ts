const SESSION_TOKEN_STORAGE_KEY = "iurisync_session_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let unauthorizedHandler: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler;
}

export function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  { skipUnauthorizedHandling = false }: { skipUnauthorizedHandling?: boolean } = {}
): Promise<T> {
  const token = getStoredToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401 && token && !skipUnauthorizedHandling) {
    // Había una sesión guardada y el backend la rechazó (expiró o fue
    // revocada en otro lugar) — se limpia y se notifica para volver al
    // login. Un 401 de un intento de login/registro (sin token todavía)
    // no entra aquí: cae al manejo genérico de abajo, que preserva el
    // detail real que mandó el backend (ej. "Usuario o contraseña
    // incorrectos").
    //
    // Solo se limpia la sesión si el token guardado AHORA sigue siendo el
    // mismo con el que se hizo esta petición: si mientras tanto el usuario
    // volvió a iniciar sesión (una petición vieja, con el token anterior,
    // que llega tarde), no se debe cerrar la sesión nueva y válida que ya
    // reemplazó a la que falló.
    if (getStoredToken() === token) {
      clearStoredToken();
      unauthorizedHandler?.();
    }
    throw new ApiError(401, "Sesión inválida o expirada");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // el cuerpo no era JSON; se mantiene el texto de estado HTTP
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
