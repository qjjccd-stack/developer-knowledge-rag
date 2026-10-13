"""真实生成服务的小样本 HTTP 并发实验；与本机故障注入和离线测试分别记录。"""

import argparse
import json
import platform
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import PROJECT_ROOT
from eval.common import copy_catalog, evaluation_settings, latency_summary
from eval.run_stability import ask_once
from eval.runtime import running_service

QUESTIONS = [
    "When should I use Celery rather than BackgroundTasks for heavy computation?",
    "Which headers make an OPTIONS request a CORS preflight?",
    "Which application attribute replaces dependencies in tests?",
    "Which path operation parameter defines response models and filters private output data?",
]


def main() -> None:
    """临时服务只在进程环境中取得授权密钥，ask_once 记录真实生成并发与实际消耗。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-ticket-config", action="store_true")
    parser.add_argument("--requests-per-level", type=int, default=4)
    parser.add_argument("--output", default="reports/live-stability.json")
    args = parser.parse_args()
    if not 4 <= args.requests_per_level <= 20:
        parser.error("真实服务实验每档 4 至 20 次请求")
    settings = evaluation_settings(args.reuse_ticket_config)
    if settings.llm_provider != "compatible" or not settings.llm_api_key.get_secret_value():
        parser.error("需要真实生成配置")
    with TemporaryDirectory(prefix="rag-live-stability-") as temp:
        db = Path(temp) / "catalog.sqlite3"
        copy_catalog(settings.db_path, db)
        overrides = {
            "RAG_LLM_PROVIDER": "compatible",
            "RAG_LLM_MODEL": settings.llm_model,
            "RAG_LLM_API_KEY": settings.llm_api_key.get_secret_value(),
            "RAG_LLM_BASE_URL": settings.llm_base_url,
            "RAG_LLM_TIMEOUT_SECONDS": str(settings.llm_timeout_seconds),
        }
        with running_service(db, overrides) as base:
            cold = ask_once(base, QUESTIONS[0])
            groups = {}
            for concurrency in (1, 2, 4):

                def run(index):
                    """ask_once 向真实服务提交固定样本，top_k 保持五，记录实际 HTTP 延迟。"""
                    return ask_once(base, QUESTIONS[index % len(QUESTIONS)])

                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    rows = list(pool.map(run, range(args.requests_per_level)))
                groups[str(concurrency)] = {**latency_summary(rows), "rows": rows}
                print(concurrency, json.dumps(latency_summary(rows)), flush=True)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "model": settings.llm_model,
        "platform": platform.platform(),
        "cold_first_live_query": cold,
        "concurrency": groups,
        "scope": "small local HTTP sample with live LLM; operational status, not answer accuracy",
        "passed": cold["ok"] and all(g["failures"] == 0 for g in groups.values()),
    }
    output = PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
