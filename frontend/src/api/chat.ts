import { apiUrl } from "./client";
import type { SourceInfo } from "../types";

export interface SSECallbacks {
  onSession: (sessionId: string) => void;
  onReferences: (sources: SourceInfo[]) => void;
  onReasoning: (text: string) => void;
  onContent: (text: string) => void;
  onDone: () => void;
  onError: (text: string) => void;
}

export async function sendMessageSSE(
  sessionId: string,
  message: string,
  callbacks: SSECallbacks,
): Promise<void> {
  const res = await fetch(apiUrl("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    callbacks.onError(err.detail || `请求失败 (${res.status})`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const d = JSON.parse(line.slice(6));
        if (d.type === "session") callbacks.onSession(d.session_id);
        else if (d.type === "references") callbacks.onReferences(d.sources || []);
        else if (d.type === "reasoning") callbacks.onReasoning(d.text);
        else if (d.type === "content") callbacks.onContent(d.text);
        else if (d.type === "done") callbacks.onDone();
        else if (d.type === "error") callbacks.onError(d.text);
      } catch {
        // skip malformed lines
      }
    }
  }
}
