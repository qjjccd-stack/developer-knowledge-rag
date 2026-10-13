"""上游内存检索接口；SQLite 持久化由 catalog.py 负责。"""

from dataclasses import dataclass, field

import numpy as np

from app.rag.chunking import Chunk


@dataclass
class IndexedChunk:
    """片段、向量与当前快照编号；初始化由 dataclass 生成。"""

    chunk: Chunk
    embedding: np.ndarray
    id: int


@dataclass
class VectorStore:
    """单次请求的可见文档快照，不共享可变排名和 top_k。"""

    chunks: list[IndexedChunk] = field(default_factory=list)
    _matrix: np.ndarray | None = None

    def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None:
        """校验数量和有效值；IndexedChunk 保存条目，清除矩阵缓存。"""
        if len(chunks) != len(embeddings) or not np.isfinite(embeddings).all():
            raise ValueError("无效的片段向量")
        start = len(self.chunks)
        self.chunks.extend(
            IndexedChunk(c, e, start + i)
            for i, (c, e) in enumerate(zip(chunks, embeddings, strict=True))
        )
        self._matrix = None

    @property
    def matrix(self) -> np.ndarray:
        """np.stack 拼接矩阵；缓存仅用于当前请求快照。"""
        if self._matrix is None:
            self._matrix = (
                np.stack([c.embedding for c in self.chunks])
                if self.chunks
                else np.empty((0, 0), dtype=np.float32)
            )
        return self._matrix

    def dense_search(self, query_vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        """矩阵乘法算余弦；稳定 argsort 在同分时保持快照顺序。"""
        if k < 1:
            raise ValueError("k 必须大于 0")
        if not self.chunks:
            return []
        scores = self.matrix @ query_vec
        ids = np.argsort(-scores, kind="stable")[:k]
        return [(int(i), float(scores[i])) for i in ids]

    def __len__(self) -> int:
        """len 返回当前快照片段数。"""
        return len(self.chunks)
