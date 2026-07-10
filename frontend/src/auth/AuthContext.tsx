import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { clearStoredApiKey, getStoredApiKey, registerUnauthorizedHandler, setStoredApiKey } from "../api/client";

interface AuthContextValue {
  apiKey: string | null;
  login: (key: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKey] = useState<string | null>(() => getStoredApiKey());

  useEffect(() => {
    registerUnauthorizedHandler(() => setApiKey(null));
  }, []);

  function login(key: string) {
    setStoredApiKey(key);
    setApiKey(key);
  }

  function logout() {
    clearStoredApiKey();
    setApiKey(null);
  }

  return <AuthContext.Provider value={{ apiKey, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}
