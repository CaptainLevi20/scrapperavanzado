import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchMe, logoutRequest } from "../api/auth";
import { clearStoredToken, getStoredToken, registerUnauthorizedHandler, setStoredToken } from "../api/client";

interface AuthContextValue {
  username: string | null;
  token: string | null;
  isAdmin: boolean;
  isLoading: boolean;
  login: (token: string, username: string, isAdmin?: boolean) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [username, setUsername] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(() => getStoredToken() !== null);

  useEffect(() => {
    registerUnauthorizedHandler(() => {
      setToken(null);
      setUsername(null);
      setIsAdmin(false);
    });
  }, []);

  useEffect(() => {
    const storedToken = getStoredToken();
    if (!storedToken) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (!cancelled) {
          setUsername(me.username);
          setIsAdmin(me.is_admin);
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearStoredToken();
          setToken(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function login(newToken: string, newUsername: string, newIsAdmin = false) {
    setStoredToken(newToken);
    setToken(newToken);
    setUsername(newUsername);
    setIsAdmin(newIsAdmin);
  }

  async function logout() {
    try {
      await logoutRequest();
    } catch {
      // best-effort: la sesión local se limpia igual aunque la llamada falle
    }
    clearStoredToken();
    setToken(null);
    setUsername(null);
    setIsAdmin(false);
  }

  return (
    <AuthContext.Provider value={{ username, token, isAdmin, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}
