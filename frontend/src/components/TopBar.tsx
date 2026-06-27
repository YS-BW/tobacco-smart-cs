import { useApp } from "../context/AppContext";
import styles from "./TopBar.module.css";

interface Props {
  onNewChat: () => void;
}

export default function TopBar({ onNewChat }: Props) {
  const { state, dispatch } = useApp();

  const toggle = (panel: "sidebar" | "kb" | "stats") =>
    dispatch({ type: "TOGGLE_PANEL", panel });

  return (
    <div className={styles.topBar} onClick={(e) => e.stopPropagation()}>
      <div className={styles.tabBar}>
        <button
          className={`${styles.tabBtn} ${state.panels.sidebar ? styles.active : ""}`}
          onClick={() => toggle("sidebar")}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          对话
        </button>
        <button
          className={`${styles.tabBtn} ${state.panels.kb ? styles.active : ""}`}
          onClick={() => toggle("kb")}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 2.5h10a1 1 0 011 1v9a1 1 0 01-1 1H3a1 1 0 01-1-1v-9a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.2" />
            <path d="M5 5h6M5 7.5h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          知识库
        </button>
        <button
          className={`${styles.tabBtn} ${state.panels.stats ? styles.active : ""}`}
          onClick={() => toggle("stats")}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <rect x="2" y="8" width="3" height="5" rx="0.5" stroke="currentColor" strokeWidth="1.2" />
            <rect x="6.5" y="5" width="3" height="8" rx="0.5" stroke="currentColor" strokeWidth="1.2" />
            <rect x="11" y="2.5" width="3" height="10.5" rx="0.5" stroke="currentColor" strokeWidth="1.2" />
          </svg>
          统计
        </button>
      </div>
      <div className={styles.newChatWrap}>
        <button className={styles.newChat} onClick={onNewChat}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          新会话
        </button>
      </div>
    </div>
  );
}
