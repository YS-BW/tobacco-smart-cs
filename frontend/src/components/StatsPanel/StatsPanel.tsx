import { useEffect } from "react";
import { useApp } from "../../context/AppContext";
import { fetchStats, fetchHotQuestions } from "../../api/stats";
import styles from "./StatsPanel.module.css";

export default function StatsPanel() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    if (!state.panels.stats) return;
    Promise.all([fetchStats(), fetchHotQuestions()])
      .then(([stats, questions]) => {
        dispatch({ type: "SET_STATS", stats });
        dispatch({ type: "SET_HOT_QUESTIONS", questions });
      })
      .catch(console.error);
  }, [state.panels.stats, dispatch]);

  const s = state.stats;

  return (
    <>
      <div className={styles.cards}>
        <div className={styles.card}>
          <div className={styles.cardLabel}>总会话数</div>
          <div className={styles.cardValue}>{s?.total_sessions ?? "-"}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>总消息数</div>
          <div className={styles.cardValue}>{s?.total_messages ?? "-"}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>知识库文档</div>
          <div className={styles.cardValue}>{s?.total_docs ?? "-"}</div>
        </div>
        <div className={styles.card}>
          <div className={styles.cardLabel}>命中率</div>
          <div className={styles.cardValue}>
            {s?.kb_hit_rate ?? "-"}
            {s && <span className={styles.cardUnit}>%</span>}
          </div>
        </div>
      </div>
      <div className={styles.hotSection}>
        <div className={styles.hotHeader}>热门问题</div>
        <ul className={styles.hotList}>
          {state.hotQuestions.length === 0 ? (
            <li style={{ padding: "var(--space-4) var(--space-6)", color: "var(--meta)", fontSize: "var(--text-sm)" }}>暂无数据</li>
          ) : (
            state.hotQuestions.map((q, i) => (
              <li key={i} className={styles.hotItem}>
                <span className={styles.hotRank}>{i + 1}</span>
                <span className={styles.hotText}>{q.question}</span>
                <span className={styles.hotCount}>{q.count} 次</span>
              </li>
            ))
          )}
        </ul>
      </div>
    </>
  );
}
