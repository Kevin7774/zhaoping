import { apiClient } from "../../shared/api/client";

export const AUTH_TOKEN_KEY = "zhaoping_auth_token";
export const AUTH_USER_KEY = "zhaoping_auth_user";

export type AuthUser = {
  userId: string;
  orgId: string;
  email: string;
  name?: string | null;
};

export type AuthOrg = {
  orgId: string;
  name: string;
  domain: string;
};

export type AuthSession = {
  accessToken: string;
  tokenType: "bearer" | string;
  user: AuthUser;
  org: AuthOrg;
};

apiClient.setJwtTokenProvider(getStoredAuthToken);

export async function loginWithCompanyEmail(email: string, name?: string): Promise<AuthSession> {
  const session = await apiClient.post<AuthSession>("/auth/login", {
    email: email.trim(),
    ...(name?.trim() ? { name: name.trim() } : {}),
  });
  storeAuthSession(session);
  return session;
}

export function storeAuthSession(session: AuthSession) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_TOKEN_KEY, session.accessToken);
  window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(session.user));
}

export function getStoredAuthToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredAuthUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const user = parsed as Partial<AuthUser>;
    return typeof user.email === "string" && typeof user.userId === "string" && typeof user.orgId === "string"
      ? (user as AuthUser)
      : null;
  } catch {
    return null;
  }
}

export function signOut() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
}
