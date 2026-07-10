import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { apiKey } = useAuth();
  if (!apiKey) return <Navigate to="/login" replace />;
  return <Outlet />;
}
