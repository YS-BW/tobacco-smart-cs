import type { DocStatusMsg } from "../types";

const WS_BASE = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
  .replace(/^http/, "ws");

export function connectKnowledgeWS(
  onMessage: (msg: DocStatusMsg) => void,
): { close: () => void } {
  let ws: WebSocket | null = null;
  let reconnectTimer: number | undefined;
  let closed = false;

  const connect = () => {
    if (closed) return;
    ws = new WebSocket(`${WS_BASE}/api/ws/knowledge`);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as DocStatusMsg;
        onMessage(msg);
      } catch {
        // skip
      }
    };
    ws.onclose = () => {
      ws = null;
      if (!closed) {
        reconnectTimer = window.setTimeout(connect, 3000);
      }
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
      }
      if (ws) {
        ws.onclose = null;
        ws.close();
        ws = null;
      }
    },
  };
}
