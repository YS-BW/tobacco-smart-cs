import { apiFetch, apiUrl } from "./client";
import type { Session, Message } from "../types";

export const fetchSessions = () => apiFetch<Session[]>("/api/sessions");

export const createSession = (title?: string) =>
  apiFetch<Session>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title }),
  });

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(apiUrl(`/api/sessions/${sessionId}/messages`), {
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 404) {
    throw new Error("HTTP 404: 会话不存在");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  const json = await res.json();
  return json.data ?? json;
}

export const deleteSession = (sessionId: string) =>
  apiFetch<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
