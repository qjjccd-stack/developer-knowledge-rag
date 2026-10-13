"""延续上游 BM25 + 向量 + RRF；分离真实相似度、融合分数与重排分数。"""

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from app.rag.chunking import Chunk
from app.rag.store import VectorStore

STOP_WORDS = set("a an the is are of to for in on how what can do does i my with and".split())


@dataclass(frozen=True)
class RetrievalResult:
    """一条候选证据；score 是当前排名分数，各检索通道分数单独保存。"""

    chunk: Chunk
    score: float
    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None


def _tokenize(text: str) -> list[str]:
    """re.findall 保留技术标识符；中文切为字和二元组；过滤常见英文虚词。"""
    tokens = re.findall(r"[a-z0-9_]+(?:[-.][a-z0-9_]+)*|[\u4e00-\u9fff]+", text.lower())
    result = []
    for token in tokens:
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            result.extend(token)
            result.extend(token[i : i + 2] for i in range(len(token) - 1))
        elif token not in STOP_WORDS:
            result.append(token)
    return result


class HybridRetriever:
    """仅处理 Catalog 已过滤权限的快照，不能接触不可见文档。"""

    def __init__(self, store: VectorStore, embedder, rrf_k: int = 60):
        """_tokenize 建词表，BM25Okapi 建当前快照的关键词索引。"""
        self.store, self.embedder, self.rrf_k = store, embedder, rrf_k
        self._corpus_tokens = [_tokenize(c.chunk.text) or ["__empty__"] for c in store.chunks]
        self._bm25 = BM25Okapi(self._corpus_tokens) if self._corpus_tokens else None
        if self._bm25:
            frequencies = Counter(t for doc in self._corpus_tokens for t in set(doc))
            n = len(self._corpus_tokens)
            # 平滑正 IDF；只有一篇可见资料时，命中的词也应有正分。
            self._bm25.idf = {
                term: math.log1p((n - df + 0.5) / (df + 0.5)) for term, df in frequencies.items()
            }

    def retrieve(self, query: str, k: int = 20, mode: str = "hybrid") -> list[RetrievalResult]:
        """dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。"""
        if k < 1 or mode not in {"dense", "bm25", "hybrid"}:
            raise ValueError("无效检索参数")
        if not self.store.chunks:
            return []
        dense = (
            self.store.dense_search(self.embedder.encode_query(query), len(self.store))
            if mode != "bm25"
            else []
        )
        dense_scores = dict(dense)
        raw_bm25 = self._bm25.get_scores(_tokenize(query))
        sparse_ids = [int(i) for i in np.argsort(-raw_bm25, kind="stable") if raw_bm25[i] > 0]
        if mode == "dense":
            scores = dict(dense[:k])
        elif mode == "bm25":
            scores = {i: float(raw_bm25[i]) for i in sparse_ids[:k]}
        else:
            scores = {}
            for lane in ([i for i, _ in dense[:k]], sparse_ids[:k]):
                for rank, idx in enumerate(lane, 1):
                    scores[idx] = scores.get(idx, 0) + 1 / (self.rrf_k + rank)
        ranked = sorted(scores, key=lambda i: (-scores[i], i))[:k]
        return [
            RetrievalResult(
                self.store.chunks[i].chunk, scores[i], dense_scores.get(i), float(raw_bm25[i])
            )
            for i in ranked
        ]
