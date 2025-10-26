export type Role = "user" | "assistant" | "tool" | "system";

export interface AuthInfo {
  token: string;
  email: string;
  role: string;
  displayName: string;
  activeSessionId: string | null;
}

export interface SessionMeta {
  id: string;
  name: string;
  createdAt: string;
  owner?: string | null;
  isActive: boolean;
}

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface ProgressEntry {
  type?: string;
  timestamp: string;
  message: string;
  tool?: string | null;
  stage?: string | null;
  level?: string | null;
}

export interface AnalysisConfig {
  news: boolean;
  fundamentals: boolean;
  market: boolean;
  sentiment: boolean;
}

export interface ThinkingStatusPayload {
  actor: string;
  label?: string;
  status: "start" | "stop" | "error";
  message?: string;
}

export interface ThinkingContentPayload {
  actor: string;
  label?: string;
  content: string;
}
