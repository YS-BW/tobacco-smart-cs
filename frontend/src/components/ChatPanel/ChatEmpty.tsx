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
        <img src="/omlx.svg" alt="AI" width="48" height="48" />
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
