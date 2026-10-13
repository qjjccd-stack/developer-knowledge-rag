"""评测公共工具：隔离知识库、临时读取授权配置、统计真实运行结果。"""

import sqlite3
from pathlib import Path

import numpy as np
from dotenv import dotenv_values
from pydantic import SecretStr

from app.config import PROJECT_ROOT, Settings


def evaluation_settings(reuse_ticket_config: bool = False) -> Settings:
    """Settings 读取 RAG 配置；显式开启时 dotenv_values 临时读取工单密钥，不写入文件。"""
    settings = Settings()
    if not reuse_ticket_config:
        return settings
    values = dotenv_values(PROJECT_ROOT.parents[1] / ".env")
    provider, separator, model = (values.get("MODEL") or "").partition("/")
    if not separator or provider not in {"deepseek", "openai"}:
        raise ValueError("工单项目的 MODEL 配置不受支持")
    key = values.get("DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY")
    if not key:
        raise ValueError("工单项目没有对应服务商的密钥")
    base_url = values.get("DEEPSEEK_BASE_URL" if provider == "deepseek" else "OPENAI_BASE_URL")
    return settings.model_copy(
        update={
            "llm_provider": "compatible",
            "llm_model": model,
            "llm_api_key": SecretStr(key),
            "llm_base_url": base_url
            or (
                "https://api.deepseek.com"
                if provider == "deepseek"
                else "https://api.openai.com/v1"
            ),
        }
    )


def copy_catalog(source: Path, destination: Path) -> None:
    """sqlite3.backup 创建包括 WAL 已提交数据的一致副本；评测不修改用户知识库。"""
    if not source.is_file():
        raise ValueError("请先完成知识库入库")
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as target:
            src.backup(target)


def latency_summary(rows: list[dict]) -> dict:
    """np.percentile 汇总实际墙钟时间；明确失败率与样本数，不把小样本称为 SLA。"""
    values = [r["elapsed_ms"] for r in rows]
    failures = sum(not r["ok"] for r in rows)
    return {
        "requests": len(rows),
        "failures": failures,
        "failure_rate": failures / len(rows) if rows else None,
        "p50_ms": float(np.percentile(values, 50)) if values else None,
        "p95_ms": float(np.percentile(values, 95)) if values else None,
        "max_ms": max(values) if values else None,
    }
