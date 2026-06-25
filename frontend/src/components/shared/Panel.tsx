import { useEffect, type ReactNode } from "react";
import styles from "./Panel.module.css";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  compact?: boolean;
  children: ReactNode;
}

export default function Panel({ isOpen, onClose, title, compact, children }: Props) {
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  return (
    <aside
      className={`${styles.panel} ${isOpen ? styles.open : ""} ${compact ? styles.compact : ""}`}
      onClick={(e) => e.stopPropagation()}
    >
      <div className={styles.header}>
        <div className={styles.brand}>{title}</div>
        <button className={styles.close} onClick={onClose} title="收起">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className={styles.body}>{children}</div>
    </aside>
  );
}
