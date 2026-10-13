"""保留上游 RAG 编排结构，增加权限快照、请求隔离和阶段耗时。"""

from dataclasses import asdict
from time import perf_counter

from app.auth import Principal
from app.config import Settings, get_settings
from app.rag.catalog import Catalog
from app.rag.cost import usage_report
from app.rag.embeddings import Embedder
from app.rag.evidence import select_context
from app.rag.generation import Generator
from app.rag.reranking import Reranker
from app.rag.retrieval import HybridRetriever

MODES = ("dense", "bm25", "hybrid", "hybrid_rerank")


class RAGPipeline:
    """应用级只读模型对象 + 每请求独立检索快照；不改变共享配置。"""

    def __init__(
        self, settings: Settings | None = None, embedder=None, reranker=None, generator=None
    ):
        """构造 Catalog 与可延迟加载的组件；允许测试注入组件，避免下载模型。"""
        self.settings = settings or get_settings()
        self.catalog = Catalog(self.settings)
        self.embedder = embedder or Embedder(self.settings)
        self.reranker = reranker or Reranker(self.settings)
        self.generator = generator or Generator(self.settings)

    def retrieve(
        self,
        question: str,
        principal: Principal,
        mode: str = "hybrid_rerank",
        top_k: int = 5,
        store=None,
    ):
        """snapshot 先过滤权限；HybridRetriever 召回，按模式 Reranker 重排，记录分阶段耗时。"""
        if mode not in MODES or not 1 <= top_k <= 10 or not question.strip():
            raise ValueError("无效问答参数")
        start = perf_counter()
        snapshot = (
            store
            if store is not None
            else self.catalog.snapshot(principal, self.embedder.fingerprint)
        )
        snap_time = perf_counter()
        retriever = HybridRetriever(snapshot, self.embedder)
        lane = "hybrid" if mode == "hybrid_rerank" else mode
        candidates = retriever.retrieve(question, max(self.settings.candidate_k, top_k), lane)
        recall_time = perf_counter()
        results = (
            self.reranker.rerank(question, candidates, top_k)
            if mode == "hybrid_rerank"
            else candidates[:top_k]
        )
        end = perf_counter()
        return results, {
            "snapshot_ms": (snap_time - start) * 1000,
            "retrieval_ms": (recall_time - snap_time) * 1000,
            "rerank_ms": (end - recall_time) * 1000,
            "total_ms": (end - start) * 1000,
            "visible_chunks": len(snapshot),
            "candidates": len(candidates),
        }

    def query(
        self,
        question: str,
        principal: Principal,
        mode: str = "hybrid_rerank",
        top_k: int = 5,
        answer_language: str = "auto",
    ) -> dict:
        """retrieve 召回，select_context 补齐授权证据，generate 校验引用与语言，统计耗时和消耗。"""
        start = perf_counter()
        snapshot = self.catalog.snapshot(principal, self.embedder.fingerprint)
        snapshot_ms = (perf_counter() - start) * 1000
        results, timings = self.retrieve(question, principal, mode, top_k, store=snapshot)
        timings["snapshot_ms"] = snapshot_ms
        reliable, context_selection = select_context(
            results,
            snapshot,
            self.settings.min_dense_score,
            mode,
            self.settings.context_max_chunks,
            query=question,
        )
        generation_start = perf_counter()
        generated = self.generator.generate(question, reliable, answer_language)
        citations = [{"id": i, **asdict(reliable[i - 1].chunk)} for i in generated.citations]
        timings["generation_ms"] = (perf_counter() - generation_start) * 1000
        timings["total_ms"] = (perf_counter() - start) * 1000
        return {
            "answer": generated.answer,
            "status": generated.status,
            "reason": generated.reason,
            "generation_mode": generated.provider,
            "claims": generated.claims,
            "validation_failure": generated.validation_failure,
            "answer_language": generated.answer_language,
            "language_check": generated.language_check,
            "generation_attempts": generated.attempts,
            "citation_contract": generated.citation_contract,
            "context_selection": context_selection,
            "context": [asdict(r) for r in reliable],
            "citations": citations,
            "retrieved": [asdict(r) for r in results],
            "timings": timings,
            "usage": usage_report(generated.input_tokens, generated.output_tokens, self.settings),
        }
