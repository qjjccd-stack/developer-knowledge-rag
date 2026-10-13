"""用本地 ONNX 模型计算真实语义向量。"""

from threading import Lock

import numpy as np

from app.config import Settings
from app.rag.model_files import model_path


class Embedder:
    """保留上游 Embedder 接口，首次使用时加载模型。"""

    def __init__(self, settings: Settings):
        """保存配置并建立 Lock；构造时不下载模型。"""
        self.settings = settings
        self.fingerprint = (
            f"fastembed-0.7.4:{settings.embedding_model}:"
            f"{settings.embedding_revision}:normalized-v1"
        )
        self._model = None
        self._lock = Lock()

    def _load(self):
        """锁内首次构造 TextEmbedding，避免多个请求同时加载。"""
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(
                    self.settings.embedding_model,
                    cache_dir=str(self.settings.model_cache),
                    threads=2,
                    specific_model_path=model_path(
                        self.settings.model_cache,
                        self.settings.embedding_model,
                        self.settings.embedding_revision,
                    ),
                )
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        """passage_embed 算文档向量，np.linalg.norm 做 L2 归一化。"""
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors = np.array(list(self._load().passage_embed(texts, batch_size=32)), dtype=np.float32)
        return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)

    def encode_query(self, query: str) -> np.ndarray:
        """query_embed 算查询向量，再归一化；与文档使用同一模型。"""
        vector = np.array(next(iter(self._load().query_embed(query))), dtype=np.float32)
        return vector / max(float(np.linalg.norm(vector)), 1e-12)
