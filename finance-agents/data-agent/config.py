"""应用配置，从 .env 文件加载。"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


# ── LLM 配置 ─────────────────────────────────────────────────────────────────
# 通用配置（默认使用的 LLM）
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # openai / qwen / deepseek

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# Qwen (通义千问) — 兼容 OpenAI 接口
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen-plus")

# DeepSeek — 兼容 OpenAI 接口
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Zhipu AI — 检索相关 API
ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", "")
ZHIPU_BASE_URL: str = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
ZHIPU_EMBEDDING_MODEL: str = os.getenv("ZHIPU_EMBEDDING_MODEL", "embedding-3")
ZHIPU_RERANK_MODEL: str = os.getenv("ZHIPU_RERANK_MODEL", "rerank")
ZHIPU_EMBEDDING_DIMENSIONS: int = int(os.getenv("ZHIPU_EMBEDDING_DIMENSIONS", "1024"))
ZHIPU_TIMEOUT_SECONDS: float = float(os.getenv("ZHIPU_TIMEOUT_SECONDS", "30"))

# ── 服务器 ────────────────────────────────────────────────────────────────────
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8100"))

# ── 数据库 ────────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://tally_user:123456@localhost:5432/tally",
)

# ── Finance MCP ───────────────────────────────────────────────────────────────
# 使用 127.0.0.1 替代 localhost，避免 Sangfor 等安全软件代理导致的 502 错误
FINANCE_MCP_BASE_URL: str = os.getenv("FINANCE_MCP_BASE_URL", "http://127.0.0.1:3335")
FINANCE_MCP_UPLOAD_DIR: str = os.getenv(
    "FINANCE_MCP_UPLOAD_DIR",
    str(Path(__file__).resolve().parents[3] / "finance-mcp" / "uploads"),
)

# ── 上传 ──────────────────────────────────────────────────────────────────────
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", FINANCE_MCP_UPLOAD_DIR)
MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))
