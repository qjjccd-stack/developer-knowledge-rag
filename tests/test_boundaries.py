"""业务边界测试：不越权、不读旧版本、不伪造引用、不共享请求参数。"""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.auth import DEMO_ADMIN, DEMO_READER, Principal, token_map
from app.config import Settings
from app.main import create_app
from app.rag.catalog import DocumentInput
from app.rag.chunking import Chunk, chunk_text
from app.rag.generation import Claim, Draft, Evidence, Generator, validate_draft
from app.rag.retrieval import HybridRetriever, RetrievalResult, _tokenize
from app.rag.store import VectorStore
from eval.metrics import evidence_metrics


def add(
    pipeline,
    doc_id="one",
    text="# Topic\nalpha answer is in this document.",
    department="public",
    principal=DEMO_ADMIN,
):
    """DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。"""
    return pipeline.catalog.upsert(
        DocumentInput(doc_id=doc_id, title=doc_id, text=text, department=department),
        principal,
        pipeline.embedder,
    )


def test_incremental_skips_embedding(pipeline):
    """重复 upsert 不调用 encode；摘要未变化时没有重复片段。"""
    first = add(pipeline)
    count = pipeline.embedder.calls
    second = add(pipeline)
    assert first["status"] == "created" and second["status"] == "unchanged"
    assert pipeline.embedder.calls == count
    assert len(pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)) == 1


def test_update_removes_old_chunks(pipeline):
    """upsert 替换版本后 snapshot 只有新原文和新版本。"""
    old = add(pipeline)
    new = add(pipeline, text="# New\nbeta new version answer.")
    chunks = pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint).chunks
    assert new["revision"] != old["revision"]
    assert (
        len(chunks) == 1 and "beta" in chunks[0].chunk.text and "alpha" not in chunks[0].chunk.text
    )


def test_failed_embedding_preserves_version(pipeline):
    """替换 encode 使其抛错；upsert 失败后 snapshot 保持原文。"""
    add(pipeline)

    def fail(texts):
        """测试故障注入：模拟模型不可用。"""
        raise RuntimeError("model unavailable")

    pipeline.embedder.encode = fail
    with pytest.raises(RuntimeError):
        add(pipeline, text="beta replacement")
    assert (
        "alpha"
        in pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)
        .chunks[0]
        .chunk.text
    )


def test_nonfinite_embedding_rejected(pipeline):
    """encode 返回 NaN 时 upsert 拒绝写入，documents 仍为空。"""
    pipeline.embedder.encode = lambda texts: np.array([[np.nan, 0, 1]])
    with pytest.raises(ValueError):
        add(pipeline)
    assert pipeline.catalog.documents(DEMO_ADMIN) == []


def test_changed_model_rejected(pipeline):
    """修改 fingerprint 后 snapshot 和 upsert 都拒绝混合模型。"""
    add(pipeline)
    pipeline.embedder.fingerprint = "different-model"
    with pytest.raises(ValueError):
        pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)
    with pytest.raises(ValueError):
        add(pipeline, "new")


def test_delete_cascades(pipeline):
    """Catalog.delete 后 snapshot 不再检索到该文档片段。"""
    add(pipeline)
    assert pipeline.catalog.delete("one", DEMO_ADMIN)
    assert len(pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)) == 0


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid", "hybrid_rerank"])
def test_acl_before_retrieval(pipeline, mode):
    """高相关 ops 片段不进入读者快照；retrieve 始终命中可见 public 片段。"""
    add(pipeline, "public", "alpha public evidence.")
    add(pipeline, "secret", "alpha alpha alpha secret evidence.", "ops")
    results, timing = pipeline.retrieve("alpha", DEMO_READER, mode, top_k=1)
    assert [r.chunk.source for r in results] == ["public"]
    assert timing["visible_chunks"] == 1


def test_department_reader(pipeline):
    """snapshot 给 ops 身份运维资料，普通读者不可见。"""
    add(pipeline, department="ops")
    ops = Principal("ops", "demo", ("ops",))
    assert len(pipeline.catalog.snapshot(ops, pipeline.embedder.fingerprint)) == 1
    assert pipeline.catalog.documents(DEMO_READER, "one") == []


def test_tenant_isolation_even_admin(pipeline):
    """Catalog.snapshot 对管理员仍执行租户过滤。"""
    add(pipeline, "other", principal=Principal("admin2", "other", (), True))
    assert len(pipeline.catalog.snapshot(DEMO_ADMIN, pipeline.embedder.fingerprint)) == 0


def test_acl_metadata_change_invalidates_revision(pipeline):
    """把 public 改为 ops 时 upsert 改版，读者立即失去资料可见性。"""
    old = add(pipeline)
    new = add(pipeline, department="ops")
    assert old["revision"] != new["revision"]
    assert not pipeline.catalog.documents(DEMO_READER)


def test_reader_cannot_write(pipeline):
    """直接调用 Catalog 写方法也会检查 admin，而非只依靠 HTTP 路由。"""
    with pytest.raises(PermissionError):
        add(pipeline, principal=DEMO_READER)
    with pytest.raises(PermissionError):
        pipeline.catalog.delete("one", DEMO_READER)


def test_heading_line_metadata():
    """chunk_text 保留章节和原始行号，不跨标题重叠。"""
    chunks = chunk_text("# First\nalpha\n## Second\nbeta", chunk_size=100, chunk_overlap=0)
    assert [(c.heading, c.start_line, c.end_line) for c in chunks] == [
        ("First", 1, 2),
        ("Second", 3, 4),
    ]


def test_chunk_bounds_and_empty():
    """chunk_text 拆长行且保持字符上限；空输入没有片段，非法 overlap 拒绝。"""
    assert not chunk_text("")
    assert all(len(c) <= 100 for c in chunk_text("x" * 501, chunk_size=100, chunk_overlap=20))
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=100, chunk_overlap=100)


def test_code_heading_is_not_section():
    """chunk_text 不把代码围栏里的 # 注释当作 Markdown 标题。"""
    text = "# Real\n" + chr(96) * 3 + "python\n# comment\n" + chr(96) * 3
    assert len(chunk_text(text)) == 1


def test_technical_and_cjk_tokens():
    """_tokenize 保留技术标识符，并拆分中文而非当成一个长单词。"""
    tokens = _tokenize("X-Forwarded-For SQLITE_BUSY 蓝牙连接")
    assert "x-forwarded-for" in tokens and "sqlite_busy" in tokens and "蓝牙" in tokens


def test_rrf_real_cosine_score(pipeline):
    """HybridRetriever 返回真实余弦而不是通道排名；dense_search 确保可解释性。"""
    add(pipeline)
    store = pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)
    result = HybridRetriever(store, pipeline.embedder).retrieve("alpha")[0]
    assert result.dense_score == pytest.approx(1.0)
    assert result.score != result.dense_score


def test_dense_tie_is_stable():
    """dense_search 同分时维持索引顺序；非法 k 被拒绝。"""
    store = VectorStore()
    store.add([Chunk("a", "a", 0), Chunk("b", "b", 0)], np.array([[1, 0], [1, 0]]))
    assert store.dense_search(np.array([1, 0]), 2) == [(0, 1.0), (1, 1.0)]
    with pytest.raises(ValueError):
        store.dense_search(np.array([1, 0]), 0)


def evidence_result():
    """RetrievalResult 构造可核验的固定引用材料。"""
    return [
        RetrievalResult(Chunk("Background tasks execute after returning a response.", "doc", 0), 1)
    ]


@pytest.mark.parametrize(
    "quote,id",
    [
        ("Background tasks execute", 99),
        ("Tasks always run before requests", 1),
        (" " * 20, 1),
    ],
)
def test_invalid_citations_rejected(quote, id):
    """validate_draft 拒绝越界 ID、伪造原文与纯空白摘录。"""
    draft = Draft(claims=[Claim(text="statement", evidence=[Evidence(id=id, quote=quote)])])
    with pytest.raises(ValueError):
        validate_draft(draft, evidence_result())


def test_only_used_citations_returned():
    """validate_draft 仅返回陈述使用的引用，不把所有检索候选视为引用。"""
    draft = Draft(
        claims=[
            Claim(text="statement", evidence=[Evidence(id=1, quote="Background tasks execute")])
        ]
    )
    assert validate_draft(draft, evidence_result() * 3) == [1]


def test_inline_citation_cannot_be_invented():
    """validate_draft 不接受模型在正文插入额外引用标号。"""
    draft = Draft(
        claims=[
            Claim(
                text="statement [99]", evidence=[Evidence(id=1, quote="Background tasks execute")]
            )
        ]
    )
    with pytest.raises(ValueError):
        validate_draft(draft, evidence_result())


def test_empty_evidence_abstains():
    """Generator 在无证据时拒答，且不返回引用和伪造 Token 使用量。"""
    result = Generator(Settings(_env_file=None)).generate("question", [])
    assert result.status == "abstained" and result.citations == [] and result.input_tokens is None


def test_parallel_requests_keep_own_topk(pipeline):
    """并行 retrieve 的 top_k 互不影响，参数不写入共享 settings。"""
    for i in range(8):
        add(pipeline, str(i), f"alpha public document number {i}.")

    def run(k):
        """retrieve 用请求自己的 k 检索；返回实际结果数量。"""
        return len(pipeline.retrieve("alpha", DEMO_READER, "dense", k)[0])

    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = list(pool.map(run, [1, 5, 2, 7]))
    assert counts == [1, 5, 2, 7] and pipeline.settings.candidate_k == 20


def test_http_auth_and_body(pipeline):
    """TestClient 验证认证、越权、客户端自报身份与 top_k 范围边界。"""
    add(pipeline, department="ops")
    client = TestClient(create_app(pipeline.settings, pipeline))
    reader = {"Authorization": "Bearer demo-reader-token"}
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers=reader).json() == []
    assert client.get("/api/documents/one", headers=reader).status_code == 404
    assert client.delete("/api/documents/one", headers=reader).status_code == 403
    assert (
        client.post(
            "/api/ask", headers=reader, json={"question": "alpha", "admin": True}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/ask", headers=reader, json={"question": "alpha", "top_k": 0}).status_code
        == 422
    )
    assert client.post("/api/ask", headers=reader, json={"question": "  "}).status_code == 422
    assert (
        client.post("/api/ask", headers=reader, json={"question": "alpha"}).json()["status"]
        == "abstained"
    )


def test_nonlocal_demo_auth_rejected():
    """token_map 对非本机地址拒绝默认演示令牌。"""
    with pytest.raises(ValueError):
        token_map(Settings(host="0.0.0.0", _env_file=None))


def test_metric_requires_relevant_passage():
    """evidence_metrics 即使找到同一文档但缺少答案段落，也不得计为命中。"""
    results = [RetrievalResult(Chunk("unrelated paragraph", "doc", 0), 1)]
    metrics = evidence_metrics(results, [{"doc_id": "doc", "quote": "actual answer"}])
    assert metrics["evidence_recall_at_k"] == 0


def test_multievidence_metrics():
    """evidence_metrics 只找齐一半资料时 coverage 为 1/2，All-Gold 为 0。"""
    metrics = evidence_metrics(
        evidence_result(),
        [
            {"doc_id": "doc", "quote": "Background tasks execute"},
            {"doc_id": "other", "quote": "another fact"},
        ],
    )
    assert metrics["evidence_recall_at_k"] == 0.5 and metrics["all_gold_at_k"] == 0


def test_chunk_id_stable():
    """chunk_text 的相同原文生成相同 ID，不同内容生成不同 ID。"""
    a = chunk_text("alpha", "doc")[0]
    b = chunk_text("alpha", "doc")[0]
    assert a.chunk_id == b.chunk_id
    assert a.chunk_id != chunk_text("beta", "doc")[0].chunk_id
