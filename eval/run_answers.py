"""真实生成与边界评测；机械检查、助手复核、人类评分分别记录。"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.auth import DEMO_ADMIN, DEMO_READER, Principal
from app.config import PROJECT_ROOT
from app.rag.catalog import DocumentInput
from app.rag.chunking import Chunk
from app.rag.generation import CONTRACT_VERSION, MAX_EVIDENCE_REFERENCES, GenerationUnavailable
from app.rag.pipeline import RAGPipeline
from app.rag.retrieval import RetrievalResult
from eval.common import copy_catalog, evaluation_settings
from eval.metrics import evidence_metrics

IDENTITIES = {
    "admin": DEMO_ADMIN,
    "reader": DEMO_READER,
    "ops": Principal("eval-ops", "demo", ("ops",)),
    "other_tenant_admin": Principal("eval-other", "other-tenant", (), True),
}


def mechanical_review(case: dict, result: dict) -> dict:
    """检查状态、候选及实际模型上下文的权限与合成标记；字串检查不能代替语义评审。"""
    forbidden = set(case.get("forbidden_documents", []))
    found = {r["chunk"]["source"] for r in result["retrieved"]}
    supplied = {r["chunk"]["source"] for r in result.get("context", [])}
    cited = {r["source"] for r in result["citations"]}
    seen = found | supplied | cited
    behavior = case["expected_behavior"]
    status_ok = (
        result["status"] == "abstained"
        if behavior == "abstain"
        else result["status"] == "answered"
        if behavior in {"answer_from_evidence", "correct_false_premise"}
        else result["status"] in {"answered", "abstained"}
    )
    leaks = [s for s in case.get("forbidden_strings", []) if s in result["answer"]]
    return {
        "expected_status_met": status_ok,
        "forbidden_document_seen": sorted(seen & forbidden),
        "forbidden_string_seen": bool(leaks),
        "citations_present_for_answer": bool(result["citations"])
        if result["status"] == "answered"
        else not result["citations"],
        "boundary_pass": status_ok and not (seen & forbidden) and not leaks,
        "scope": "status and access boundaries only; not semantic answer accuracy",
    }


def answer_summary(rows: list[dict]) -> dict:
    """汇总 API 实际 usage、错误及边界结果；未填人工或助手评分不算通过。"""
    groups = {}
    for row in rows:
        category = row["category"]
        group = groups.setdefault(category, {"cases": 0, "errors": 0, "boundary_passes": 0})
        group["cases"] += 1
        group["errors"] += row["status"] == "error"
        group["boundary_passes"] += bool(row.get("mechanical_review", {}).get("boundary_pass"))
    usage = [r.get("usage") or {} for r in rows]
    return {
        "cases": len(rows),
        "live_responses_with_usage": sum(u.get("input_tokens") is not None for u in usage),
        "input_tokens": sum(u.get("input_tokens") or 0 for u in usage),
        "output_tokens": sum(u.get("output_tokens") or 0 for u in usage),
        "groups": groups,
        "human_reviewed": sum(r.get("human_review", {}).get("correct") is not None for r in rows),
        "assistant_reviewed": sum(
            r.get("assistant_review", {}).get("correct") is not None for r in rows
        ),
    }


def main() -> None:
    """副本中 query 执行真实生成；逐题保存可续跑报告，记录证据并留下待评审字段。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dataset", default="eval/answer_cases.json")
    parser.add_argument("--output", default="reports/answer-review.json")
    parser.add_argument("--reuse-ticket-config", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 4))
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit 必须大于 0")
    settings = evaluation_settings(args.reuse_ticket_config)
    if settings.llm_provider != "compatible" or not settings.llm_api_key.get_secret_value():
        parser.error("先配置真实生成模型和 API Key；不会用摘录模式冒充真实评测")
    raw = (PROJECT_ROOT / args.dataset).read_bytes()
    dataset = json.loads(raw)
    cases = [c for c in dataset["cases"] if not args.ids or c["id"] in args.ids][: args.limit]
    if args.ids and set(args.ids) - {c["id"] for c in cases}:
        parser.error("选中的题目 ID 不存在或超出 limit")
    cases = [
        {
            **case,
            "base_id": case["id"],
            "repeat": repeat,
            "id": case["id"] if args.repeat == 1 else case["id"] + f".r{repeat + 1}",
        }
        for repeat in range(args.repeat)
        for case in cases
    ]
    path = PROJECT_ROOT / args.output
    digest = hashlib.sha256(raw).hexdigest()
    rows = []
    if args.resume and path.is_file():
        old = json.loads(path.read_text())
        if old["dataset_sha256"] != digest or old["model"] != settings.llm_model:
            parser.error("旧报告的数据集或模型不同，不能续跑")
        rows = old["rows"]
    done = {r["id"] for r in rows}
    with TemporaryDirectory(prefix="rag-answer-eval-") as temp:
        db = Path(temp) / "catalog.sqlite3"
        copy_catalog(settings.db_path, db)
        pipeline = RAGPipeline(settings.model_copy(update={"db_path": db}))
        for fixture in dataset.get("fixtures", []):
            pipeline.catalog.upsert(DocumentInput(**fixture), DEMO_ADMIN, pipeline.embedder)
        snapshot = pipeline.catalog.snapshot(DEMO_ADMIN, pipeline.embedder.fingerprint)
        for case in cases:
            if case["id"] in done:
                continue
            start = perf_counter()
            base = {**case, "gold": case.get("evidence", [])}
            diagnostics = []
            pipeline.generator.diagnostic_sink = diagnostics.append
            try:
                result = pipeline.query(
                    case["question"],
                    IDENTITIES[case["identity"]],
                    answer_language=case.get("answer_language", "auto"),
                )
                base.update(result)
                base["mechanical_review"] = mechanical_review(case, result)
                retrieved = [
                    RetrievalResult(Chunk(**r["chunk"]), r["score"]) for r in result["retrieved"]
                ]
                base["gold_retrieval"] = (
                    evidence_metrics(retrieved, base["gold"]) if base["gold"] else None
                )
            except Exception as exc:
                base.update({"status": "error", "error_type": type(exc).__name__})
                if isinstance(exc, GenerationUnavailable):
                    base["error_code"] = exc.code
            base["elapsed_ms"] = (perf_counter() - start) * 1000
            base["generation_diagnostics"] = diagnostics
            base["human_review"] = {"correct": None, "all_claims_supported": None, "notes": ""}
            base["assistant_review"] = {"correct": None, "all_claims_supported": None, "notes": ""}
            rows.append(base)
            report = {
                "created_at": datetime.now(UTC).isoformat(),
                "dataset_sha256": digest,
                "snapshot_sha256": hashlib.sha256(
                    "".join(c.chunk.revision + c.chunk.chunk_id for c in snapshot.chunks).encode()
                ).hexdigest(),
                "model": settings.llm_model,
                "configuration": {
                    "citation_contract": CONTRACT_VERSION,
                    "context_max_chunks": settings.context_max_chunks,
                    "max_generation_attempts": settings.generation_max_attempts,
                    "max_claims": 6,
                    "max_refs_per_claim": MAX_EVIDENCE_REFERENCES,
                    "prompt_revision": "focused-v2",
                    "repeat": args.repeat,
                    "min_dense_score": settings.min_dense_score,
                },
                "requested": len(cases),
                "summary": answer_summary(rows),
                "rows": rows,
                "scope": "live generation; curated development set; human review separate",
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                case["id"],
                base["status"],
                base.get("reason", base.get("error_code", "")),
                flush=True,
            )


if __name__ == "__main__":
    main()
