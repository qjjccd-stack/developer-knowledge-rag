"""本地 Cross-Encoder 重排，保留召回分数用于诊断。"""

from dataclasses import replace
from threading import Lock

from app.config import Settings
from app.rag.model_files import model_path
from app.rag.retrieval import RetrievalResult


class Reranker:
    """复用上游重排职责，以 FastEmbed/ONNX 替代 Torch。"""

    def __init__(self, settings: Settings):
        """保存模型配置，Lock 保护首次加载；不在初始化时联网。"""
        self.settings, self._model = settings, None
        self._lock = Lock()

    def _load(self):
        """锁内构造 TextCrossEncoder；已加载时直接复用只读模型。"""
        with self._lock:
            if self._model is None:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                self._model = TextCrossEncoder(
                    self.settings.reranker_model,
                    cache_dir=str(self.settings.model_cache),
                    threads=2,
                    specific_model_path=model_path(
                        self.settings.model_cache,
                        self.settings.reranker_model,
                        self.settings.reranker_revision,
                    ),
                )
        return self._model

    def rerank(self, query: str, results: list[RetrievalResult], top_n: int = 5):
        """模型 rerank 计算相关性；replace 增加重排分数；sorted 截取最高结果。"""
        if not results:
            return []
        scores = list(self._load().rerank(query, [r.chunk.text for r in results], batch_size=16))
        ranked = [
            replace(r, score=float(s), rerank_score=float(s))
            for r, s in zip(results, scores, strict=True)
        ]
        return sorted(ranked, key=lambda r: (-r.score, r.chunk.source, r.chunk.index))[:top_n]
