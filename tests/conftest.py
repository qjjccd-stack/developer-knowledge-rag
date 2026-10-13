"""边界测试注入小向量，单元测试不需要下载模型或付费接口。"""

import json

import numpy as np
import pytest

from app.config import Settings
from app.rag.pipeline import RAGPipeline


class FakeEmbedder:
    """仅用于逻辑测试，不参与真实模型评测。"""

    fingerprint = "test-only-vector-v1"
    calls = 0

    def encode(self, texts):
        """encode_query 逐条产生测试向量；记录调用数以验证增量跳过。"""
        self.calls += 1
        return np.array([self.encode_query(t) for t in texts], dtype=np.float32)

    def encode_query(self, text):
        """按 alpha/beta/gamma 生成固定向量并归一化，便于精确断言权限过滤结果。"""
        vector = np.array([float(word in text.lower()) for word in ("alpha", "beta", "gamma")])
        if not vector.any():
            vector = np.array([0, 0, 1.0])
        return vector / np.linalg.norm(vector)


class PassReranker:
    """仅用于逻辑测试的稳定重排替身。"""

    def rerank(self, query, results, top_n):
        """切片保留调用方要求数量；真实重排模型通过独立 benchmark 验证。"""
        return results[:top_n]


@pytest.fixture
def pipeline(tmp_path):
    """Settings 指向临时库，RAGPipeline 注入测试组件，隔离真实知识库。"""
    settings = Settings(db_path=tmp_path / "catalog.db", _env_file=None)
    return RAGPipeline(settings, embedder=FakeEmbedder(), reranker=PassReranker())


@pytest.fixture
def review_paths(tmp_path):
    """建立一题合成报告，其中 AI 结论故意不可信，用于验证审核页面不暴露预评分。"""
    source = tmp_path / "source.json"
    output = tmp_path / "human.json"
    source.write_text(
        json.dumps(
            {
                "requested": 1,
                "dataset_sha256": "synthetic-dataset",
                "model": "synthetic-no-live-model",
                "rows": [
                    {
                        "id": "Q001",
                        "question": "Synthetic question?",
                        "status": "answered",
                        "answer": "Synthetic response.",
                        "claims": [],
                        "citations": [],
                        "assistant_review": {"correct": True, "notes": "DO_NOT_SHOW_AI_GRADE"},
                        "mechanical_review": {
                            "boundary_pass": True,
                            "citations_present_for_answer": True,
                        },
                    }
                ],
            }
        )
    )
    return source, output
