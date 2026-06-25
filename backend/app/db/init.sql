-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '新对话',
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    reasoning_content TEXT,
    `references` TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 压缩摘要表
CREATE TABLE IF NOT EXISTS session_compressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    compressed_topics TEXT NOT NULL,
    round_start INTEGER NOT NULL,
    round_end INTEGER NOT NULL,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'done', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 问答日志
CREATE TABLE IF NOT EXISTS qa_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_question TEXT NOT NULL,
    retrieved_doc_ids TEXT,
    max_similarity REAL,
    kb_hit INTEGER DEFAULT 0,
    response_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 知识库文档记录
CREATE TABLE IF NOT EXISTS knowledge_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'processing' CHECK(status IN ('processing', 'ready', 'failed')),
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
