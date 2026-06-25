import { useCallback } from "react";
import styles from "./InputArea.module.css";

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
}

export default function InputArea({ onSend, disabled, inputRef }: Props) {
  const handleSend = useCallback(() => {
    const text = inputRef.current?.value.trim();
    if (!text || disabled) return;
    onSend(text);
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.style.height = "auto";
    }
  }, [onSend, disabled, inputRef]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = inputRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
    }
  };

  return (
    <div className={styles.inputArea} onClick={(e) => e.stopPropagation()}>
      <div className={styles.inputWrap}>
        <textarea
          ref={inputRef}
          rows={1}
          placeholder="输入消息… (Enter 发送，Shift+Enter 换行)"
          onKeyDown={handleKeyDown}
          onInput={handleInput}
        />
        <button className={styles.sendBtn} onClick={handleSend} disabled={disabled}>
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
