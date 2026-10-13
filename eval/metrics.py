"""证据片段级检索指标；词语重合不被称作忠实度或幻觉率。"""


def normalize(text: str) -> str:
    """split/join 统一空白，使跨行但内容一致的摘录可以匹配。"""
    return " ".join(text.split())


def evidence_metrics(results, golds: list[dict], k: int = 5) -> dict:
    """按文档 ID + 原文摘录判定命中，计算证据覆盖率、Any/All-Gold@K 和 MRR。"""
    hits = [
        [
            r.chunk.source == g["doc_id"] and normalize(g["quote"]) in normalize(r.chunk.text)
            for g in golds
        ]
        for r in results[:k]
    ]
    found = [any(row[i] for row in hits) for i in range(len(golds))]
    first = next((rank for rank, row in enumerate(hits, 1) if any(row)), None)
    return {
        "evidence_recall_at_k": sum(found) / len(golds) if golds else None,
        "any_gold_at_k": float(any(found)) if golds else None,
        "all_gold_at_k": float(all(found)) if golds else None,
        "mrr_at_k": 1 / first if first else 0.0,
    }


def recall_at_k(retrieved_sources: list[str], relevant_sources: list[str], k: int) -> float:
    """保留上游文档级兼容指标；新评测使用 evidence_metrics 避免仅找到文档就算成功。"""
    return (
        sum(s in retrieved_sources[:k] for s in set(relevant_sources)) / len(set(relevant_sources))
        if relevant_sources
        else 0.0
    )


def mrr(retrieved_sources: list[str], relevant_sources: list[str]) -> float:
    """保留上游 MRR 辅助函数；enumerate 寻找首个相关来源的倒数排名。"""
    return next(
        (1 / i for i, source in enumerate(retrieved_sources, 1) if source in relevant_sources), 0.0
    )
