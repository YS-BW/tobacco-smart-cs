import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Message, SourceInfo, StreamingState } from "../../types";
import styles from "./Messages.module.css";

function SourceCards({ sources }: { sources: SourceInfo[] }) {
  if (!sources.length) return null;
  return (
    <div className={styles.sourcesBlock}>
      <div className={styles.sourcesHeader}>
        <span className={styles.sourcesMark}></span>
        <span>知识库引用</span>
      </div>
      <div className={styles.sources}>
        {sources.map((s) => (
          <SourceCard key={s.index} source={s} />
        ))}
      </div>
    </div>
  );
}

function SourceCard({ source }: { source: SourceInfo }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className={`${styles.sourceCard} ${expanded ? styles.expanded : ""}`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className={styles.sourceName}>
        <span className={styles.sourceIndex}>{source.index}</span>
        <span>{source.filename}</span>
      </div>
      <div className={styles.sourceSnippet}>{source.content}</div>
    </div>
  );
}

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const text = String(children).replace(/\n$/, "");
          if (match) {
            return (
              <SyntaxHighlighter style={oneLight as any} language={match[1]} PreTag="pre">
                {text}
              </SyntaxHighlighter>
            );
          }
          return <code className={className} {...props}>{children}</code>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

/** Static message from history */
export function HistoryMessage({ message }: { message: Message }) {
  if (message.role === "user") {
    return (
      <div className={`${styles.row} ${styles.user}`}>
        <div className={styles.avatar}>你</div>
        <div className={styles.body}>
          <div className={styles.bubble}>{message.content}</div>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.row} ${styles.ai}`}>
      <div className={styles.avatar}>AI</div>
      <div className={styles.body}>
        {message.references && <SourceCards sources={message.references} />}
        <div className={styles.bubble}>
          <MarkdownContent content={message.content} />
        </div>
      </div>
    </div>
  );
}

/** Streaming AI message (actively receiving) */
export function StreamingMessage({ streaming }: { streaming: StreamingState }) {
  return (
    <div className={`${styles.row} ${styles.ai}`}>
      <div className={styles.avatar}>AI</div>
      <div className={styles.body}>
        {streaming.sources.length > 0 && <SourceCards sources={streaming.sources} />}
        {streaming.isActive && !streaming.content ? (
          <div className={styles.loadingDots}><span></span><span></span><span></span></div>
        ) : streaming.content ? (
          <div className={styles.bubble}>
            <MarkdownContent content={streaming.content} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
