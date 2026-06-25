import { useEffect, useRef, useState, useCallback } from "react";
import { useApp } from "../../context/AppContext";
import { fetchDocs, uploadFiles, deleteDoc } from "../../api/knowledge";
import { connectKnowledgeWS } from "../../api/ws";
import styles from "./KBPanel.module.css";

const TYPE_LABELS: Record<string, string> = {
  pdf: "PDF", word: "Word", image: "图片", markdown: "Markdown",
};
const STATUS_LABELS: Record<string, string> = {
  ready: "就绪", processing: "处理中", failed: "失败",
};

export default function KBPanel() {
  const { state, dispatch } = useApp();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragover, setDragover] = useState(false);
  const wsRef = useRef<ReturnType<typeof connectKnowledgeWS> | null>(null);

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
    try {
      await uploadFiles(files);
      // Refresh doc list
      const docs = await fetchDocs();
      dispatch({ type: "SET_DOCS", docs });
    } catch (e: any) {
      alert(e.message || "上传失败");
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
    handleUpload(e.dataTransfer.files);
  };

  return (
    <>
      <div
        className={`${styles.upload} ${dragover ? styles.dragover : ""}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
        onDragLeave={() => setDragover(false)}
        onDrop={handleDrop}
      >
        <div className={styles.uploadIcon}>
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <path d="M20 6v20M12 14l8-8 8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M6 28v4a2 2 0 002 2h24a2 2 0 002-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>
        <div className={styles.uploadText}>拖拽文件到此处，或点击上传</div>
        <div className={styles.uploadHint}>支持 PDF / Word / 图片 / Markdown 格式</div>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp,.md"
          onChange={(e) => e.target.files && handleUpload(e.target.files)}
        />
      </div>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr><th>文件名</th><th>类型</th><th>分块数</th><th>状态</th><th>操作</th></tr>
          </thead>
          <tbody>
            {state.docs.length === 0 ? (
              <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--meta)" }}>暂无文档</td></tr>
            ) : (
              state.docs.map((doc) => (
                <tr key={doc.id}>
                  <td>{doc.filename}</td>
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
    </>
  );
}
