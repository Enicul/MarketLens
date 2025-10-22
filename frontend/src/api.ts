import type { AnalysisConfig, AuthInfo, ChatMessage, ProgressEntry, SessionMeta } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers ?? {})
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    const detail = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const message =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String(detail.detail)
        : response.statusText;
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export interface LoginPayload {
  email?: string;
  password?: string;
  guest?: boolean;
}

export interface LoginResult {
  token: string;
  email: string;
  role: string;
  display_name: string;
  active_session_id: string | null;
}

export async function login(payload: LoginPayload): Promise<AuthInfo> {
  const result = await request<LoginResult>("/api/login", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return {
    token: result.token,
    email: result.email,
    role: result.role,
    displayName: result.display_name,
    activeSessionId: result.active_session_id
  };
}

export async function logout(token: string): Promise<void> {
  await request("/api/logout", { method: "POST" }, token);
}

export async function fetchAnalysisConfig(token: string): Promise<AnalysisConfig> {
  const result = await request<{ config: AnalysisConfig }>("/api/analysis-config", {}, token);
  return result.config;
}

export async function updateAnalysisConfig(token: string, config: Partial<AnalysisConfig>): Promise<AnalysisConfig> {
  const result = await request<{ config: AnalysisConfig }>(
    "/api/analysis-config",
    {
      method: "PUT",
      body: JSON.stringify(config)
    },
    token
  );
  return result.config;
}

export async function resetAnalysisConfig(token: string): Promise<AnalysisConfig> {
  const result = await request<{ config: AnalysisConfig }>(
    "/api/analysis-config/reset",
    { method: "POST" },
    token
  );
  return result.config;
}

interface SessionWire {
  id: string;
  name: string;
  created_at: string;
  owner?: string | null;
  is_active?: boolean;
}

export async function listSessions(token: string): Promise<SessionMeta[]> {
  const result = await request<SessionWire[]>("/api/sessions", {}, token);
  return result.map((item) => ({
    id: item.id,
    name: item.name,
    createdAt: item.created_at,
    owner: item.owner ?? undefined,
    isActive: Boolean(item.is_active)
  }));
}

export async function createSession(token: string, name?: string): Promise<SessionMeta> {
  const result = await request<SessionWire>(
    "/api/sessions",
    {
      method: "POST",
      body: JSON.stringify({ name })
    },
    token
  );
  return {
    id: result.id,
    name: result.name,
    createdAt: result.created_at,
    owner: result.owner ?? undefined,
    isActive: Boolean(result.is_active)
  };
}

export async function renameSession(token: string, sessionId: string, name: string): Promise<void> {
  await request(`/api/sessions/${sessionId}`, {
    method: "PUT",
    body: JSON.stringify({ name })
  }, token);
}

export async function deleteSession(token: string, sessionId: string): Promise<void> {
  await request(`/api/sessions/${sessionId}`, { method: "DELETE" }, token);
}

export async function activateSession(token: string, sessionId: string): Promise<void> {
  await request(`/api/sessions/${sessionId}/activate`, { method: "POST" }, token);
}

export async function fetchSessionMessages(token: string, sessionId: string): Promise<ChatMessage[]> {
  const result = await request<{ messages: ChatMessage[] }>(
    `/api/sessions/${sessionId}/messages`,
    {},
    token
  );
  return result.messages;
}

export async function fetchSessionProgress(token: string, sessionId: string): Promise<ProgressEntry[]> {
  const result = await request<{ progress: ProgressEntry[] }>(
    `/api/sessions/${sessionId}/progress`,
    {},
    token
  );
  return result.progress ?? [];
}
