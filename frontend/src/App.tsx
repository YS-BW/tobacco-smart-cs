import { useEffect, useCallback } from "react";
import { AppProvider, useApp } from "./context/AppContext";
import TopBar from "./components/TopBar";
import Panel from "./components/shared/Panel";
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel/ChatPanel";
import KBPanel from "./components/KBPanel/KBPanel";
import StatsPanel from "./components/StatsPanel/StatsPanel";
import { fetchSessions, deleteSession } from "./api/sessions";
import styles from "./App.module.css";

function AppInner() {
  const { state, dispatch } = useApp();

  // Load sessions on mount
  useEffect(() => {
    fetchSessions()
      .then((sessions) => dispatch({ type: "SET_SESSIONS", sessions }))
      .catch(console.error);
  }, [dispatch]);

  const handleNewChat = useCallback(() => {
    dispatch({ type: "SET_ACTIVE_SESSION", sessionId: null });
    dispatch({ type: "SET_MESSAGES", messages: [] });
    dispatch({ type: "CLOSE_ALL_PANELS" });
  }, [dispatch]);

  const handleSelectSession = useCallback((id: string) => {
    dispatch({ type: "SET_ACTIVE_SESSION", sessionId: id });
    dispatch({ type: "CLOSE_ALL_PANELS" });
  }, [dispatch]);

  const handleDeleteSession = useCallback(async (id: string) => {
    try {
      await deleteSession(id);
      if (state.activeSessionId === id) {
        dispatch({ type: "SET_ACTIVE_SESSION", sessionId: null });
        dispatch({ type: "SET_MESSAGES", messages: [] });
      }
      const sessions = await fetchSessions();
      dispatch({ type: "SET_SESSIONS", sessions });
    } catch (e) {
      console.error(e);
    }
  }, [state.activeSessionId, dispatch]);

  const closeAll = useCallback(() => {
    dispatch({ type: "CLOSE_ALL_PANELS" });
  }, [dispatch]);

  return (
    <div className={styles.app}>
      {/* Sidebar Panel */}
      <Panel
        isOpen={state.panels.sidebar}
        onClose={() => dispatch({ type: "TOGGLE_PANEL", panel: "sidebar" })}
        title="烟草智能客服"
        compact
      >
        <Sidebar onSelect={handleSelectSession} onDelete={handleDeleteSession} />
      </Panel>

      {/* Main Area */}
      <div className={styles.main} onClick={closeAll}>
        <TopBar onNewChat={handleNewChat} />
        <ChatPanel />
      </div>

      {/* KB Panel */}
      <Panel
        isOpen={state.panels.kb}
        onClose={() => dispatch({ type: "TOGGLE_PANEL", panel: "kb" })}
        title="知识库"
      >
        <KBPanel />
      </Panel>

      {/* Stats Panel */}
      <Panel
        isOpen={state.panels.stats}
        onClose={() => dispatch({ type: "TOGGLE_PANEL", panel: "stats" })}
        title="数据统计"
      >
        <StatsPanel />
      </Panel>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppInner />
    </AppProvider>
  );
}
