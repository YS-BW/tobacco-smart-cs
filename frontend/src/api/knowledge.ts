import { apiFetch, apiUrl } from "./client";
import type { KnowledgeDoc } from "../types";

export const fetchDocs = () =>
  apiFetch<KnowledgeDoc[]>("/api/knowledge/documents");

export async function uploadFiles(files: FileList | File[]): Promise<KnowledgeDoc[]> {
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
  const body = await res.json();
  return body.data?.docs ?? [];
}

export async function uploadFile(file: File): Promise<KnowledgeDoc[]> {
  return uploadFiles([file]);
}

export const deleteDoc = (docId: number) =>
  apiFetch<void>(`/api/knowledge/documents/${docId}`, { method: "DELETE" });

export const fetchDocContent = (filename: string) =>
  apiFetch<{ filename: string; content: string }>(
    `/api/knowledge/content/${encodeURIComponent(filename)}`,
  );
