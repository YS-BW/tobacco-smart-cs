import styles from "./ChatEmpty.module.css";

interface Props {
  onUseHint: (text: string) => void;
}

const HINTS = [
  "黄鹤楼有哪些系列？",
  "如何办理烟草专卖许可证？",
  "卷烟分为哪几类？",
  "烤烟和晾烟有什么区别？",
];

export default function ChatEmpty({ onUseHint }: Props) {
  return (
    <div className={styles.empty}>
      <div className={styles.icon}>
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path d="M12 2C6.48 2 2 6.48 2 12c0 1.82.49 3.53 1.34 5L2 22l5-1.34C8.47 21.51 10.18 22 12 22c5.52 0 10-4.48 10-10S17.52 2 12 2z"
            stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="8" cy="12" r="1" fill="currentColor" />
          <circle cx="12" cy="12" r="1" fill="currentColor" />
          <circle cx="16" cy="12" r="1" fill="currentColor" />
        </svg>
      </div>
      <div className={styles.text}>有什么我可以帮你的？</div>
      <div className={styles.hints}>
        {HINTS.map((h) => (
          <div key={h} className={styles.hint} onClick={() => onUseHint(h)}>
            {h}
          </div>
        ))}
      </div>
    </div>
  );
}
