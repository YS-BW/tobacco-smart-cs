import { apiFetch, apiUrl } from "./client";
import type { KnowledgeDoc } from "../types";

export const fetchDocs = () =>
  apiFetch<KnowledgeDoc[]>("/api/knowledge/documents");

export async function uploadFiles(files: FileList | File[]): Promise<void> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(apiUrl("/api/knowledge/upload"), {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `上传失败 (${res.status})`);
  }
}

export const deleteDoc = (docId: number) =>
  apiFetch<void>(`/api/knowledge/documents/${docId}`, { method: "DELETE" });
