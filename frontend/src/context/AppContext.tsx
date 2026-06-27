import React, { createContext, useContext, useReducer, useEffect, type ReactNode } from "react";
import type { Session, Message, KnowledgeDoc, StatsOverview, TopQuestion, SourceInfo } from "../types";

interface AppState {
  sessions: Session[];
  activeSessionId: string | null;
  messages: Message[];
  streaming: {
    reasoning: string;
    content: string;
    sources: SourceInfo[];
    isActive: boolean;
  };
  docs: KnowledgeDoc[];
  stats: StatsOverview | null;
  hotQuestions: TopQuestion[];
  panels: { sidebar: boolean; kb: boolean; stats: boolean };
  theme: "light" | "dark";
}

const getSystemTheme = (): "light" | "dark" =>
  window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

const getInitialTheme = (): "light" | "dark" => {
  const saved = localStorage.getItem("theme");
  if (saved === "dark" || saved === "light") return saved;
  return getSystemTheme();
};

const initialTheme = getInitialTheme();
document.documentElement.setAttribute("data-theme", initialTheme);

const initialState: AppState = {
  sessions: [],
  activeSessionId: localStorage.getItem("activeSessionId") || null,
  messages: [],
  streaming: { reasoning: "", content: "", sources: [], isActive: false },
  docs: [],
  stats: null,
  hotQuestions: [],
  panels: { sidebar: false, kb: false, stats: false },
  theme: initialTheme,
};

type Action =
  | { type: "SET_SESSIONS"; sessions: Session[] }
  | { type: "SET_ACTIVE_SESSION"; sessionId: string | null }
  | { type: "SET_MESSAGES"; messages: Message[] }
  | { type: "APPEND_REASONING"; text: string }
  | { type: "APPEND_CONTENT"; text: string }
  | { type: "SET_SOURCES"; sources: SourceInfo[] }
  | { type: "SET_STREAMING_ACTIVE"; active: boolean }
  | { type: "RESET_STREAMING" }
  | { type: "SET_DOCS"; docs: KnowledgeDoc[] }
  | { type: "UPDATE_DOC_STATUS"; docId: number; status: string; chunkCount?: number }
  | { type: "ADD_DOCS"; docs: KnowledgeDoc[] }
  | { type: "REMOVE_DOC"; docId: number }
  | { type: "SET_STATS"; stats: StatsOverview }
  | { type: "SET_HOT_QUESTIONS"; questions: TopQuestion[] }
  | { type: "TOGGLE_PANEL"; panel: "sidebar" | "kb" | "stats" }
  | { type: "CLOSE_ALL_PANELS" }
  | { type: "TOGGLE_THEME" }
  | { type: "SET_THEME"; theme: "light" | "dark" };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_SESSIONS":
      return { ...state, sessions: action.sessions };
    case "SET_ACTIVE_SESSION":
      if (action.sessionId) localStorage.setItem("activeSessionId", action.sessionId);
      else localStorage.removeItem("activeSessionId");
      return { ...state, activeSessionId: action.sessionId };
    case "SET_MESSAGES":
      return { ...state, messages: action.messages };
    case "APPEND_REASONING":
      return { ...state, streaming: { ...state.streaming, reasoning: state.streaming.reasoning + action.text } };
    case "APPEND_CONTENT":
      return { ...state, streaming: { ...state.streaming, content: state.streaming.content + action.text } };
    case "SET_SOURCES":
      return { ...state, streaming: { ...state.streaming, sources: action.sources } };
    case "SET_STREAMING_ACTIVE":
      return { ...state, streaming: { ...state.streaming, isActive: action.active } };
    case "RESET_STREAMING":
      return { ...state, streaming: { reasoning: "", content: "", sources: [], isActive: false } };
    case "SET_DOCS":
      return { ...state, docs: action.docs };
    case "UPDATE_DOC_STATUS":
      return {
        ...state,
        docs: state.docs.map((d) =>
          d.id === action.docId
            ? { ...d, status: action.status as KnowledgeDoc["status"], chunk_count: action.chunkCount ?? d.chunk_count }
            : d,
        ),
      };
    case "ADD_DOCS":
      return { ...state, docs: [...action.docs, ...state.docs] };
    case "REMOVE_DOC":
      return { ...state, docs: state.docs.filter((d) => d.id !== action.docId) };
    case "SET_STATS":
      return { ...state, stats: action.stats };
    case "SET_HOT_QUESTIONS":
      return { ...state, hotQuestions: action.questions };
    case "TOGGLE_PANEL": {
      const isOpen = state.panels[action.panel];
      return {
        ...state,
        panels: {
          sidebar: action.panel === "sidebar" ? !isOpen : false,
          kb: action.panel === "kb" ? !isOpen : false,
          stats: action.panel === "stats" ? !isOpen : false,
        },
      };
    }
    case "CLOSE_ALL_PANELS":
      return { ...state, panels: { sidebar: false, kb: false, stats: false } };
    case "TOGGLE_THEME": {
      const newTheme = state.theme === "light" ? "dark" : "light";
      localStorage.setItem("theme", newTheme);
      document.documentElement.setAttribute("data-theme", newTheme);
      return { ...state, theme: newTheme };
    }
    case "SET_THEME": {
      document.documentElement.setAttribute("data-theme", action.theme);
      return { ...state, theme: action.theme };
    }
    default:
      return state;
  }
}

const AppContext = createContext<{ state: AppState; dispatch: React.Dispatch<Action> } | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // 始终监听系统主题变化
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent) => {
      dispatch({ type: "SET_THEME", theme: e.matches ? "dark" : "light" });
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
