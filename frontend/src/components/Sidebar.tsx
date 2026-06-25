import { useApp } from "../context/AppContext";
import styles from "./Sidebar.module.css";

interface Props {
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({ onSelect, onDelete }: Props) {
  const { state } = useApp();

  if (!state.sessions.length) {
    return <div className={styles.empty}>暂无对话</div>;
  }

  return (
    <div className={styles.list}>
      {state.sessions.map((s) => (
        <div
          key={s.id}
          className={`${styles.item} ${s.id === state.activeSessionId ? styles.active : ""}`}
          onClick={() => onSelect(s.id)}
        >
          <span className={styles.title}>{s.title}</span>
          <span
            className={styles.del}
            onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
          >
            &times;
          </span>
        </div>
      ))}
    </div>
  );
}
