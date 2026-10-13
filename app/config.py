"""独立配置；只读取本项目 .env，避免混入工单助手密钥。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """BaseSettings 解析 RAG_ 环境变量；Field 校验范围。"""

    model_config = SettingsConfigDict(
        env_prefix="RAG_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )
    db_path: Path = PROJECT_ROOT / "data" / "catalog.sqlite3"
    model_cache: Path = PROJECT_ROOT / "data" / "models"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    embedding_revision: str = "d13954661f83248295ba75c1ed411eef3b7b936e"
    reranker_revision: str = "a09144355adeed5f58c8ed011d209bf8ee5a1fec"
    chunk_size: int = Field(1200, ge=100, le=2000)
    chunk_overlap: int = Field(120, ge=0, le=200)
    candidate_k: int = Field(20, ge=1, le=100)
    min_dense_score: float = Field(0.35, ge=-1, le=1)
    llm_provider: str = "extractive"
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: float = Field(30, gt=0, le=120)
    generation_max_attempts: int = Field(2, ge=1, le=2)
    context_max_chunks: int = Field(8, ge=5, le=12)
    max_concurrent_queries: int = Field(4, ge=1, le=32)
    input_price_per_million: float | None = Field(None, ge=0)
    output_price_per_million: float | None = Field(None, ge=0)
    tokens_json: SecretStr = SecretStr("")
    allow_demo_auth: bool = True
    host: str = "127.0.0.1"
    port: int = Field(8010, ge=1024, le=65535)


@lru_cache
def get_settings() -> Settings:
    """调用 Settings() 解析并缓存配置。"""
    return Settings()
