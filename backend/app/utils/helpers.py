"""工具函数。"""

import uuid
from datetime import datetime, timezone


def gen_uuid() -> str:
    """生成 UUID 字符串。"""
    return str(uuid.uuid4())


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def detect_file_type(filename: str) -> str:
    """根据文件扩展名判断文件类型。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapping = {
        "pdf": "pdf",
        "doc": "word", "docx": "word",
        "png": "image", "jpg": "image", "jpeg": "image", "webp": "image",
        "md": "markdown",
    }
    return mapping.get(ext, "unknown")
