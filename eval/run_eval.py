"""同一知识快照上比较四种真实检索方案；生成质量必须另外验证。"""

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from statistics import mean
from time import perf_counter

from app.auth import DEMO_ADMIN
from app.config import PROJECT_ROOT
from app.rag.pipeline import MODES, RAGPipeline
from eval.metrics import evidence_metrics, normalize


def validate_set(cases: list[dict], store) -> None:
    """检查 ID 唯一及每条 gold 对应真实原文片段；避免坏标签被计为模型失败。"""
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("评测 ID 重复")
    for case in cases:
        if not case["evidence"]:
            raise ValueError("检索对照集必须包含 gold；拒答用独立边界测试")
        for gold in case["evidence"]:
            if not any(
                c.chunk.source == gold["doc_id"]
                and normalize(gold["quote"]) in normalize(c.chunk.text)
                for c in store.chunks
            ):
                raise ValueError(f"标签不在任何完整片段中：{case['id']} {gold['doc_id']}")


def main() -> None:
    """读取标注集，validate_set 校验；retrieve 执行四路对照，保存完整结果与汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="eval/tech_qa.json")
    parser.add_argument("--output", type=str, default="reports/retrieval-comparison.json")
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 6))
    args = parser.parse_args()
    raw = (PROJECT_ROOT / args.dataset).read_bytes()
    cases = json.loads(raw)["cases"]
    pipeline = RAGPipeline()
    store = pipeline.catalog.snapshot(DEMO_ADMIN, pipeline.embedder.fingerprint)
    validate_set(cases, store)
    # 排除首次模型加载耗时，但另外记录；四种模式都在热模型、同一快照下比较。
    cold = perf_counter()
    warm, _ = pipeline.retrieve(cases[0]["question"], DEMO_ADMIN, "hybrid_rerank", store=store)
    cold_ms = (perf_counter() - cold) * 1000
    del warm
    rows, summary = [], {}
    for mode in MODES:
        group = []
        for repeat in range(args.repeat):
            for case in cases:
                results, timings = pipeline.retrieve(
                    case["question"], DEMO_ADMIN, mode, store=store
                )
                metrics = evidence_metrics(results, case["evidence"])
                row = {
                    "mode": mode,
                    "repeat": repeat,
                    "id": case["id"],
                    "question": case["question"],
                    **metrics,
                    "timings": timings,
                    "retrieved": [
                        {
                            "doc_id": r.chunk.source,
                            "chunk_id": r.chunk.chunk_id,
                            "lines": [r.chunk.start_line, r.chunk.end_line],
                            "score": r.score,
                            "dense_score": r.dense_score,
                            "bm25_score": r.bm25_score,
                            "rerank_score": r.rerank_score,
                        }
                        for r in results
                    ],
                }
                rows.append(row)
                group.append(row)
        summary[mode] = {
            key: mean(r[key] for r in group)
            for key in ("evidence_recall_at_k", "any_gold_at_k", "all_gold_at_k", "mrr_at_k")
        }
        summary[mode]["mean_latency_ms"] = mean(r["timings"]["total_ms"] for r in group)
        summary[mode]["runs"] = len(group)
        print(mode, json.dumps(summary[mode]), flush=True)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "cases": len(cases),
        "repeat": args.repeat,
        "k": 5,
        "visible_documents": len(pipeline.catalog.documents(DEMO_ADMIN)),
        "visible_chunks": len(store),
        "embedding": pipeline.embedder.fingerprint,
        "reranker": pipeline.settings.reranker_model,
        "reranker_revision": pipeline.settings.reranker_revision,
        "platform": platform.platform(),
        "cold_warmup_ms": cold_ms,
        "snapshot_sha256": hashlib.sha256(
            "".join(c.chunk.revision + c.chunk.chunk_id for c in store.chunks).encode()
        ).hexdigest(),
        "scope": "curated development set; retrieval only; no blind test or live LLM evaluation",
        "summary": summary,
        "rows": rows,
    }
    output = PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
