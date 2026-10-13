"""真实模型 HTTP 并发与进程冷启动；本机上游注入故障，分别报告，不混算失败率。"""

import argparse
import json
import platform
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx

from app.config import PROJECT_ROOT, Settings
from eval.common import copy_catalog, latency_summary
from eval.runtime import fault_provider, running_service

HEADERS = {"Authorization": "Bearer demo-reader-token"}
QUESTIONS = [
    "When should I use Celery rather than BackgroundTasks for heavy computation?",
    "Can I use startup event handlers together with a lifespan parameter?",
    "Can I enable CORS credentials while keeping origins, methods and headers as wildcards?",
]


def ask_once(base: str, question: str, top_k: int = 5, mode="hybrid_rerank") -> dict:
    """httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。"""
    start = perf_counter()
    try:
        with httpx.Client(trust_env=False, timeout=60) as client:
            response = client.post(
                base + "/api/ask",
                headers=HEADERS,
                json={"question": question, "top_k": top_k, "mode": mode},
            )
        payload = response.json()
        ok = response.status_code == 200 and payload.get("status") == "answered"
        if ok:
            ok = len(payload["retrieved"]) <= top_k and all(
                not r["chunk"]["source"].startswith(("deployment.", "ops."))
                and r["chunk"]["source"] != "advanced.behind-a-proxy"
                for r in payload["retrieved"]
            )
        detail = payload.get("detail", {})
        return {
            "ok": ok,
            "http_status": response.status_code,
            "top_k": top_k,
            "mode": mode,
            "status": payload.get("status"),
            "error_code": detail.get("code") if isinstance(detail, dict) else None,
            "elapsed_ms": (perf_counter() - start) * 1000,
            "timings": payload.get("timings"),
            "usage": payload.get("usage"),
            "retrieved_count": len(payload.get("retrieved", [])),
        }
    except httpx.TransportError as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "top_k": top_k,
            "mode": mode,
            "elapsed_ms": (perf_counter() - start) * 1000,
        }


def fault_experiment(db_path) -> dict:
    """故障上游配合真实服务和 SDK，验证超时/429/500 分类、零自动重试与下一请求恢复。"""
    rows = []
    with fault_provider(["timeout", "rate_limit", "server_error", "ok"]) as (upstream, state):
        with running_service(
            db_path,
            {
                "RAG_LLM_PROVIDER": "compatible",
                "RAG_LLM_API_KEY": "synthetic-test-key",
                "RAG_LLM_BASE_URL": upstream,
                "RAG_LLM_TIMEOUT_SECONDS": "0.15",
            },
        ) as base:
            expected = ["UPSTREAM_TIMEOUT", "UPSTREAM_RATE_LIMIT", "UPSTREAM_ERROR", None]
            for code in expected:
                row = ask_once(base, QUESTIONS[0], mode="bm25")
                row["expected_code"] = code
                row["handled_as_expected"] = (
                    row.get("http_status") == 503 and row["error_code"] == code
                    if code
                    else row["ok"]
                )
                rows.append(row)
    return {
        "rows": rows,
        "upstream_requests": state["requests"],
        "passed": all(r["handled_as_expected"] for r in rows) and state["requests"] == 4,
        "scope": "real loopback HTTP and SDK; synthetic upstream; not live LLM reliability",
    }


def main() -> None:
    """副本上启动隔离服务，先测冷请求，再测热并发与故障恢复，保存可追溯运行记录。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests-per-level", type=int, default=12)
    parser.add_argument("--output", default="reports/stability.json")
    args = parser.parse_args()
    if not 4 <= args.requests_per_level <= 100:
        parser.error("每档请求数须为 4 至 100")
    settings = Settings()
    with TemporaryDirectory(prefix="rag-stability-") as temp:
        db = Path(temp) / "catalog.sqlite3"
        copy_catalog(settings.db_path, db)
        start = perf_counter()
        with running_service(db) as base:
            startup_ms = (perf_counter() - start) * 1000
            cold = ask_once(base, QUESTIONS[0])
            groups = {}
            for workers in (1, 2, 4):

                def run(index):
                    """ask_once 为每项请求传自己的问题和 top_k，线程池限制当前并发档位。"""
                    return ask_once(base, QUESTIONS[index % len(QUESTIONS)], 3 + index % 3)

                started = perf_counter()
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    rows = list(pool.map(run, range(args.requests_per_level)))
                elapsed = perf_counter() - started
                groups[str(workers)] = {
                    **latency_summary(rows),
                    "concurrency": workers,
                    "duration_seconds": elapsed,
                    "requests_per_second": len(rows) / elapsed,
                    "rows": rows,
                }
                print("concurrency", workers, json.dumps(latency_summary(rows)), flush=True)
        fault = fault_experiment(db)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "startup_to_health_ms": startup_ms,
        "cold_first_query": cold,
        "concurrency": groups,
        "fault_injection": fault,
        "scope": "local CPU; process-cold with existing weight cache; extractive answers; no SLA",
        "passed": cold["ok"]
        and all(g["failures"] == 0 for g in groups.values())
        and fault["passed"],
    }
    path = PROJECT_ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("fault_injection", fault["passed"], "overall", report["passed"], flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
