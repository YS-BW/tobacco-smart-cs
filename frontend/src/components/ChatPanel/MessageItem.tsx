import { useState, useEffect, useCallback, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { fetchDocContent } from "../../api/knowledge";
import type { Message, SourceInfo, StreamingState } from "../../types";
import styles from "./Messages.module.css";

interface GroupedSource {
  filename: string;
  indices: number[];
  chunks: string[];
}

function SourceCards({ sources }: { sources: SourceInfo[] }) {
  if (!sources.length) return null;

  // 按文件名聚合
  const grouped = sources.reduce<GroupedSource[]>((acc, s) => {
    const existing = acc.find((g) => g.filename === s.filename);
    if (existing) {
      existing.indices.push(s.index);
      existing.chunks.push(s.content);
    } else {
      acc.push({ filename: s.filename, indices: [s.index], chunks: [s.content] });
    }
    return acc;
  }, []);

  return (
    <div className={styles.sourcesBlock}>
      <div className={styles.sourcesHeader}>
        <span className={styles.sourcesMark}></span>
        <span>知识库引用</span>
      </div>
      <div className={styles.sources}>
        {grouped.map((g) => (
          <SourceCard key={g.filename} group={g} />
        ))}
      </div>
    </div>
  );
}

/** 在全文中高亮被引用的片段，并自动滚动到第一个高亮位置 */
function FullDocWithHighlights({ content, chunks }: { content: string; chunks: string[] }) {
  const highlightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!highlightRef.current) return;
    const target = highlightRef.current.querySelector(`.${styles.highlightChunk}`);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, []);

  // 用子字符串定位切分全文：chunk 在全文中出现的位置作为分割点
  const normalize = (s: string) => s.replace(/\r\n/g, "\n").trim();
  const normContent = normalize(content);
  const segments: { text: string; highlight: boolean }[] = [];
  const usedRanges: [number, number][] = [];
  let pos = 0;

  for (const chunk of chunks) {
    const normChunk = normalize(chunk);
    if (!normChunk) continue;
    const idx = normContent.indexOf(normChunk, pos);
    if (idx === -1) continue;

    // chunk 之前的普通内容
    if (idx > pos) {
      const before = normContent.slice(pos, idx).trim();
      if (before) segments.push({ text: before, highlight: false });
    }
    // chunk 本身（高亮）
    segments.push({ text: normChunk, highlight: true });
    usedRanges.push([idx, idx + normChunk.length]);
    pos = idx + normChunk.length;
  }

  // 最后剩余的普通内容
  if (pos < normContent.length) {
    const rest = normContent.slice(pos).trim();
    if (rest) segments.push({ text: rest, highlight: false });
  }

  // 如果没有匹配到任何 chunk，fallback 显示全文
  if (segments.length === 0) {
    return (
      <div ref={highlightRef} className={styles.modalMarkdown}>
        <MarkdownContent content={content} />
      </div>
    );
  }

  return (
    <div ref={highlightRef}>
      {segments.map((seg, i) => seg.highlight ? (
        <div key={i} className={styles.highlightChunk}>
          <MarkdownContent content={seg.text} />
        </div>
      ) : (
        <div key={i} className={styles.modalMarkdown}>
          <MarkdownContent content={seg.text} />
        </div>
      ))}
    </div>
  );
}

function SourcePreviewModal({ group, onClose }: { group: GroupedSource; onClose: () => void }) {
  const [showFull, setShowFull] = useState(false);
  const [fullContent, setFullContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const handleLoadFull = useCallback(() => {
    if (fullContent) { setShowFull(true); return; }
    setLoading(true);
    setError(false);
    fetchDocContent(group.filename)
      .then((data) => { setFullContent(data.content); setShowFull(true); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [group.filename, fullContent]);

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalContent} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <div className={styles.modalTitle}>
            <span className={styles.sourceIndex}>{group.indices[0]}</span>
            <span>{group.filename}</span>
          </div>
          <button className={styles.modalClose} onClick={onClose}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className={styles.modalBody}>
          {showFull && fullContent ? (
            <FullDocWithHighlights content={fullContent} chunks={group.chunks} />
          ) : (
            <>
              {group.chunks.map((content, i) => (
                <div key={i} className={styles.modalChunk}>
                  <div className={styles.chunkLabel}>片段 {group.indices[i]}</div>
                  <div className={styles.modalMarkdown}>
                    <MarkdownContent content={content} />
                  </div>
                </div>
              ))}
              <button
                className={styles.loadFullBtn}
                onClick={handleLoadFull}
                disabled={loading}
              >
                {loading ? "加载中…" : error ? "加载失败，点击重试" : "查看完整文档"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SourceCard({ group }: { group: GroupedSource }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  return (
    <>
      <div
        className={styles.sourceCard}
        onClick={() => setPreviewOpen(true)}
      >
        <div className={styles.sourceName}>
          <span className={styles.sourceIndex}>{group.indices[0]}</span>
          <span>{group.filename}</span>
          {group.chunks.length > 1 && (
            <span className={styles.cardChunkCount}>×{group.chunks.length}</span>
          )}
        </div>
      </div>
      {previewOpen && (
        <SourcePreviewModal group={group} onClose={() => setPreviewOpen(false)} />
      )}
    </>
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
      <img className={styles.avatarImg} src="/omlx.svg" alt="oMLX" />
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
      <img className={styles.avatarImg} src="/omlx.svg" alt="oMLX" />
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
