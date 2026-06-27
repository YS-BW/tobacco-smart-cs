import { useEffect, useRef, useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useApp } from "../../context/AppContext";
import { fetchDocs, uploadFile, deleteDoc, fetchDocContent } from "../../api/knowledge";
import { connectKnowledgeWS } from "../../api/ws";
import styles from "./KBPanel.module.css";
import modalStyles from "../ChatPanel/Messages.module.css";

const TYPE_LABELS: Record<string, string> = {
  pdf: "PDF", word: "Word", image: "图片", markdown: "Markdown", html: "HTML",
};
const STATUS_LABELS: Record<string, string> = {
  ready: "就绪", processing: "处理中", failed: "失败",
};
const UPLOAD_STATUS_LABELS: Record<UploadProgressItem["status"], string> = {
  waiting: "等待",
  uploading: "上传中",
  submitted: "已提交",
  failed: "失败",
};

type UploadProgressItem = {
  name: string;
  status: "waiting" | "uploading" | "submitted" | "failed";
};

function DocPreviewModal({ filename, onClose }: { filename: string; onClose: () => void }) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    fetchDocContent(filename)
      .then((data) => { if (!cancelled) setContent(data.content); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [filename]);

  return (
    <div className={modalStyles.modalOverlay} onClick={onClose}>
      <div className={modalStyles.modalContent} onClick={(e) => e.stopPropagation()}>
        <div className={modalStyles.modalHeader}>
          <div className={modalStyles.modalTitle}>
            <span>{filename}</span>
          </div>
          <button className={modalStyles.modalClose} onClick={onClose}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className={modalStyles.modalBody}>
          {loading ? (
            <div className={modalStyles.modalLoading}>
              <div className={modalStyles.loadingDots}><span></span><span></span><span></span></div>
            </div>
          ) : error ? (
            <div className={modalStyles.modalError}>加载失败</div>
          ) : (
            <div className={modalStyles.modalMarkdown}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content ?? ""}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function KBPanel() {
  const { state, dispatch } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragover, setDragover] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgressItem[]>([]);
  const [search, setSearch] = useState("");
  const wsRef = useRef<ReturnType<typeof connectKnowledgeWS> | null>(null);

  const filteredDocs = search.trim()
    ? state.docs.filter((d) => d.filename.toLowerCase().includes(search.toLowerCase()))
    : state.docs;

  // Load docs when panel opens
  useEffect(() => {
    if (state.panels.kb) {
      fetchDocs()
        .then((docs) => dispatch({ type: "SET_DOCS", docs }))
        .catch(console.error);
    }
  }, [state.panels.kb, dispatch]);

  // Connect WebSocket for real-time status updates
  useEffect(() => {
    if (!state.panels.kb) {
      wsRef.current?.close();
      wsRef.current = null;
      return;
    }

    wsRef.current = connectKnowledgeWS((msg) => {
      dispatch({
        type: "UPDATE_DOC_STATUS",
        docId: msg.doc_id,
        status: msg.status,
        chunkCount: msg.chunk_count,
      });
    });

    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [state.panels.kb, dispatch]);

  const handleUpload = useCallback(async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    setUploading(true);
    setUploadProgress(fileArray.map((f) => ({ name: f.name, status: "waiting" })));

    const updateProgress = (index: number, status: UploadProgressItem["status"]) => {
      setUploadProgress((items) =>
        items.map((item, i) => (i === index ? { ...item, status } : item)),
      );
    };

    const errors: string[] = [];

    try {
      for (const [index, file] of fileArray.entries()) {
        updateProgress(index, "uploading");
        try {
          const newDocs = await uploadFile(file);
          // 每个文件提交成功后立即插入列表，后续解析/分块/向量化由 WebSocket 更新。
          if (newDocs.length > 0) {
            dispatch({ type: "ADD_DOCS", docs: newDocs });
          }
          updateProgress(index, "submitted");
        } catch (e: any) {
          updateProgress(index, "failed");
          errors.push(`${file.name}: ${e.message || "上传失败"}`);
        }
      }

      const docs = await fetchDocs();
      dispatch({ type: "SET_DOCS", docs });

      if (errors.length > 0) {
        alert(errors.join("\n"));
      }
    } finally {
      setUploading(false);
      setUploadProgress([]);
      if (fileRef.current) {
        fileRef.current.value = "";
      }
    }
  }, [dispatch]);

  const handleDelete = useCallback(async (id: number) => {
    try {
      await deleteDoc(id);
      dispatch({ type: "REMOVE_DOC", docId: id });
    } catch (e: any) {
      alert(e.message || "删除失败");
    }
  }, [dispatch]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragover(false);
    if (uploading) return;
    handleUpload(e.dataTransfer.files);
  };

  return (
    <>
      <div
        className={`${styles.upload} ${dragover ? styles.dragover : ""} ${uploading ? styles.uploading : ""}`}
        onClick={() => !uploading && fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
        onDragLeave={() => setDragover(false)}
        onDrop={handleDrop}
      >
        <div className={styles.uploadIcon}>
          {uploading ? (
            <div className={modalStyles.loadingDots}><span></span><span></span><span></span></div>
          ) : (
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
              <path d="M20 6v20M12 14l8-8 8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M6 28v4a2 2 0 002 2h24a2 2 0 002-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          )}
        </div>
        {uploading ? (
          <div className={styles.uploadProgress}>
            <div className={styles.uploadProgressText}>正在上传 {uploadProgress.length} 个文件…</div>
            <div className={styles.uploadFileList}>
              {uploadProgress.map((item, i) => (
                <div key={`${item.name}-${i}`} className={styles.uploadFileName}>
                  <span>{item.name}</span>
                  <span className={`${styles.uploadFileStatus} ${styles[item.status]}`}>
                    {UPLOAD_STATUS_LABELS[item.status]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className={styles.uploadText}>拖拽文件到此处，或点击选择文件</div>
            <div className={styles.uploadHint}>支持批量上传 · PDF / Word / 图片 / Markdown</div>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.md,.html,.htm"
          onChange={(e) => e.target.files && handleUpload(e.target.files)}
        />
      </div>
      <div className={styles.tableWrap}>
        <div className={styles.docSummary}>
          共 <span className={styles.docCount}>{state.docs.length}</span> 个文档
          {search.trim() && <span>，找到 {filteredDocs.length} 个</span>}
        </div>
        <div className={styles.searchBar}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--ink-faint)" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input
            className={styles.searchInput}
            type="text"
            placeholder="搜索文件名…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <table className={styles.table}>
          <thead>
            <tr><th>文件名</th><th>类型</th><th>分块数</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {filteredDocs.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--meta)" }}>{search.trim() ? "无匹配文档" : "暂无文档"}</td></tr>
            ) : (
              filteredDocs.map((doc) => (
                <tr key={doc.id}>
                  <td><button className={styles.fileName} onClick={() => setPreviewDoc(doc.filename)}>{doc.filename}</button></td>
                  <td><span className={`${styles.typeBadge} ${styles[doc.file_type] || ""}`}>{TYPE_LABELS[doc.file_type] || doc.file_type}</span></td>
                  <td>{doc.chunk_count}</td>
                  <td>
                    <span className={`${styles.statusBadge} ${styles[doc.status] || ""}`}>
                      <span className={styles.statusDot}></span>
                      {STATUS_LABELS[doc.status] || doc.status}
                    </span>
                  </td>
                  <td><button className={styles.btnDelete} onClick={() => handleDelete(doc.id)}>删除</button></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {previewDoc && <DocPreviewModal filename={previewDoc} onClose={() => setPreviewDoc(null)} />}
    </>
  );
}
