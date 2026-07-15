import { apiFetch } from "./client";

export interface AuthResponse {
  token: string;
  username: string;
}

export function login(username: string, password: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function register(username: string, password: string, invite_code: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, invite_code }),
  });
}

export function logoutRequest(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function fetchMe(): Promise<{ username: string }> {
  return apiFetch<{ username: string }>("/auth/me");
}

export function changePassword(current_password: string, new_password: string): Promise<void> {
  return apiFetch<void>(
    "/auth/change-password",
    {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    },
    { skipUnauthorizedHandling: true }
  );
}
