import { useRef, useEffect, useCallback } from "react";
import { useApp } from "../../context/AppContext";
import ChatEmpty from "./ChatEmpty";
import { HistoryMessage, StreamingMessage } from "./MessageItem";
import InputArea from "./InputArea";
import { fetchMessages, fetchSessions } from "../../api/sessions";
import { sendMessageSSE } from "../../api/chat";
import { isHttpError } from "../../api/client";
import styles from "./ChatPanel.module.css";

export default function ChatPanel() {
  const { state, dispatch } = useApp();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  // 追踪当前发送操作的实际 sessionId（onSession 回调会更新它）
  const sendingSessionId = useRef<string>("");
  const sendingRef = useRef(false);

  const scrollBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (messagesRef.current) {
        messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
      }
    });
  }, []);

  // Load messages when active session changes
  useEffect(() => {
    if (!state.activeSessionId) {
      dispatch({ type: "SET_MESSAGES", messages: [] });
      return;
    }
    if (sendingRef.current) return;
    fetchMessages(state.activeSessionId)
      .then((msgs) => dispatch({ type: "SET_MESSAGES", messages: msgs }))
      .catch((error) => {
        if (isHttpError(error, 404)) {
          dispatch({ type: "SET_ACTIVE_SESSION", sessionId: null });
          dispatch({ type: "SET_MESSAGES", messages: [] });
          return;
        }
        console.error(error);
      });
  }, [state.activeSessionId, dispatch]);

  // Scroll on new messages or streaming updates
  useEffect(() => { scrollBottom(); }, [state.messages, state.streaming.content, scrollBottom]);

  const handleSend = useCallback(async (text: string) => {
    const sessionId = state.activeSessionId || "";
    sendingSessionId.current = sessionId;
    sendingRef.current = true;

    // Add user message optimistically
    const userMsg = {
      id: Date.now(),
      session_id: sessionId || "pending",
      role: "user" as const,
      content: text,
      reasoning_content: null,
      references: null,
      created_at: new Date().toISOString(),
    };
    dispatch({ type: "SET_MESSAGES", messages: [...state.messages, userMsg] });
    dispatch({ type: "RESET_STREAMING" });
    dispatch({ type: "SET_STREAMING_ACTIVE", active: true });

    try {
      await sendMessageSSE(sessionId, text, {
        onSession: (newSessionId) => {
          // 后端自动创建了会话，更新 ref 和 state
          if (!sessionId) {
            sendingSessionId.current = newSessionId;
            dispatch({ type: "SET_ACTIVE_SESSION", sessionId: newSessionId });
            fetchSessions().then((sessions) => dispatch({ type: "SET_SESSIONS", sessions }));
          }
        },
        onReferences: (sources) => dispatch({ type: "SET_SOURCES", sources }),
        onReasoning: (t) => dispatch({ type: "APPEND_REASONING", text: t }),
        onContent: (t) => dispatch({ type: "APPEND_CONTENT", text: t }),
        onDone: async () => {
          const sid = sendingSessionId.current;
          Promise.all([fetchMessages(sid), fetchSessions()]).then(
            ([msgs, sessions]) => {
              dispatch({ type: "SET_MESSAGES", messages: msgs });
              dispatch({ type: "SET_SESSIONS", sessions });
            },
          ).finally(() => {
            dispatch({ type: "RESET_STREAMING" });
            sendingRef.current = false;
          });
        },
        onError: (errText) => {
          sendingRef.current = false;
          dispatch({ type: "SET_STREAMING_ACTIVE", active: false });
          const errMsg = {
            id: Date.now() + 1,
            session_id: sendingSessionId.current || "pending",
            role: "assistant" as const,
            content: `[错误] ${errText}`,
            reasoning_content: null,
            references: null,
            created_at: new Date().toISOString(),
          };
          dispatch({ type: "SET_MESSAGES", messages: [...state.messages, userMsg, errMsg] });
          dispatch({ type: "RESET_STREAMING" });
        },
      });
    } catch {
      sendingRef.current = false;
      dispatch({ type: "SET_STREAMING_ACTIVE", active: false });
      dispatch({ type: "RESET_STREAMING" });
    }
  }, [state.messages, state.activeSessionId, dispatch]);

  const handleUseHint = useCallback((text: string) => {
    if (inputRef.current) {
      inputRef.current.value = text;
      inputRef.current.focus();
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 160) + "px";
    }
  }, []);

  const hasMessages = state.messages.length > 0 || state.streaming.isActive;

  return (
    <div className={styles.chatPanel}>
      {!hasMessages ? (
        <ChatEmpty onUseHint={handleUseHint} />
      ) : (
        <div className={styles.messages} ref={messagesRef}>
          {state.messages.map((m) => (
            <HistoryMessage key={m.id} message={m} />
          ))}
          {state.streaming.isActive && (
            <StreamingMessage streaming={state.streaming} />
          )}
        </div>
      )}
      <InputArea
        onSend={handleSend}
        disabled={state.streaming.isActive}
        inputRef={inputRef}
      />
    </div>
  );
}
