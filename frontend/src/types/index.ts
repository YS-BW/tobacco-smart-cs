export interface Session {
  id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface SourceInfo {
  index: number;
  title: string;
  filename: string;
  content: string;
}

export interface Message {
  id: number;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  reasoning_content: string | null;
  references: SourceInfo[] | null;
  created_at: string;
}

export interface KnowledgeDoc {
  id: number;
  filename: string;
  file_type: "pdf" | "word" | "image" | "markdown" | "html";
  chunk_count: number;
  status: "processing" | "ready" | "failed";
  created_at: string;
}

export interface StatsOverview {
  total_sessions: number;
  total_messages: number;
  total_docs: number;
  kb_hit_rate: number;
}

export interface TopQuestion {
  question: string;
  count: number;
}

export interface StreamingState {
  reasoning: string;
  content: string;
  sources: SourceInfo[];
  isActive: boolean;
}

export interface DocStatusMsg {
  type: "doc_status";
  doc_id: number;
  status: "processing" | "ready" | "failed";
  step: string;
  chunk_count?: number;
  error?: string;
}
