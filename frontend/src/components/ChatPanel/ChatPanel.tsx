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
      if (!messagesRef.current) return;
      const el = messagesRef.current;
      // 流式输出时始终滚到底部
      el.scrollTo({ top: el.scrollHeight, behavior: "instant" });
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
  const isDark = state.theme === "dark";

  return (
    <div className={styles.chatPanel}>
      <button
        className={styles.themeToggle}
        onClick={() => dispatch({ type: "TOGGLE_THEME" })}
        title={isDark ? "切换浅色模式" : "切换深色模式"}
      >
        {isDark ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" />
            <line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" />
            <line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        )}
      </button>
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
