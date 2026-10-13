"""验证真实失败所暴露的边界：编号引用、有限纠正、语言、关联上下文及权限。"""

import json

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.rag.evidence import code_document_id, evidence_spans, select_context
from app.rag.generation import Generator, SelectedDraft, resolve_references
from app.rag.language import answer_language, check_language
from app.rag.retrieval import RetrievalResult
from eval.run_answers import mechanical_review
from tests.test_boundaries import add, evidence_result


def test_numbered_quote_preserves_markdown():
    """模型只选 ID，resolve_references 必须还原包括链接和反引号的精确原文。"""
    text = "All origins must be [explicitly specified](https://example.org) with `credentials`."
    selected = SelectedDraft.model_validate(
        {
            "language": "en",
            "claims": [
                {
                    "text": "Origins must be explicitly listed.",
                    "evidence": [{"id": 1, "span_id": 1}],
                }
            ],
        }
    )
    draft = resolve_references(selected, [evidence_spans(text)])
    assert draft.claims[0].evidence[0].quote == text


@pytest.mark.parametrize(
    "text",
    [
        "First paragraph has enough evidence.\n\nSecond paragraph remains unchanged.",
        "x" * 1700,
        "\n  Original indentation is preserved inside this paragraph.  \n",
    ],
)
def test_every_span_is_original_substring(text):
    """长段和空白分割之后仍然引用实际子串，编号唯一且最长 800 字符。"""
    spans = evidence_spans(text)
    assert spans and all(s.quote in text and 15 <= len(s.quote) <= 800 for s in spans)
    assert [s.span_id for s in spans] == list(range(1, len(spans) + 1))


def test_model_cannot_write_quote_or_exceed_claim_limit():
    """SelectedDraft 拒绝 quote 字段及九条陈述；限制必须在提示词和校验器中一致。"""
    claim = {"text": "Some supported statement.", "evidence": [{"id": 1, "span_id": 1}]}
    with pytest.raises(ValidationError):
        SelectedDraft.model_validate({"language": "en", "claims": [claim] * 9})
    claim["evidence"][0]["quote"] = "Model invented wording"
    with pytest.raises(ValidationError):
        SelectedDraft.model_validate({"language": "en", "claims": [claim]})


def test_multiple_valid_spans_do_not_fail_old_three_reference_limit():
    """TestClient 复现中四个有效单元被旧上限误拒；保留全部证据并仍拒绝超过八个引用。"""
    text = (
        "First supported detail.\n\nSecond supported detail.\n\n"
        "Third supported detail.\n\nFourth supported detail."
    )
    references = [{"id": 1, "span_id": i} for i in range(1, 5)]
    claim = {"text": "Four related details are documented.", "evidence": references}
    selected = SelectedDraft.model_validate({"language": "en", "claims": [claim]})
    assert len(resolve_references(selected, [evidence_spans(text)]).claims[0].evidence) == 4
    claim["evidence"] = [{"id": 1, "span_id": 1}] * 9
    with pytest.raises(ValidationError):
        SelectedDraft.model_validate({"language": "en", "claims": [claim]})


@pytest.mark.parametrize(
    "text,detected",
    [
        (
            "No, si proporcionas un parámetro lifespan, los manejadores de eventos startup "
            "y shutdown ya no se llamarán; es todo lifespan o todos los eventos, no ambos.",
            "es",
        ),
        (
            "No, no puedes usar el comodín en allow_origins y allow_headers si las credenciales "
            "están habilitadas; todos deben especificarse explícitamente.",
            "es",
        ),
        ("OpenAPI schema 可以通过设置 `openapi_url=None` 来完全禁用。", "zh"),
    ],
)
def test_original_wrong_languages_are_detected(text, detected):
    """用原失败回答及相同语句检查实际文本，不相信模型自行声明 language=en。"""
    result = check_language(text, "en")
    assert result["decision"] == "mismatch" and result["detected"] == detected


def test_code_does_not_count_as_answer_language():
    """正文英文中的中文代码注释不触发语言误报；显式语言可覆盖自动判断。"""
    assert answer_language("如何创建 FastAPI TestClient？") == "zh"
    assert answer_language("如何创建 FastAPI TestClient？", "en") == "en"
    text = (
        "Create the client by passing the application into its constructor.\n"
        "```python\n# 中文注释\nclient = TestClient(app)\n```"
    )
    assert check_language(text, "en")["decision"] == "matched"
    assert check_language("`client = TestClient(app)`", "en")["decision"] == "undetermined"


def test_context_expansion_keeps_threshold_and_acl(pipeline):
    """低分邻居由可靠锚点补充，私有代码不进入读者快照；没有锚点时不扩大上下文。"""
    from app.auth import DEMO_READER

    text = "# Database\nalpha create session and yield it.\n## Cleanup\nAlways close in finally."
    add(pipeline, "guide", text)
    code = code_document_id("docs_src/dependencies/example.py")
    add(pipeline, code, "alpha private implementation", department="ops")
    store = pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)
    anchor = RetrievalResult(store.chunks[0].chunk, 1, dense_score=0.6)
    context, trace = select_context([anchor], store, 0.35, "hybrid_rerank")
    assert any("finally" in r.chunk.text for r in context)
    assert code not in {r.chunk.source for r in context}
    assert any(t["reason"] == "adjacent_context" for t in trace)
    anchor = RetrievalResult(anchor.chunk, 1, dense_score=0.326)
    assert select_context([anchor], store, 0.35, "hybrid_rerank")[0] == []


def test_inline_code_lookup_cannot_read_hidden_doc(pipeline):
    """公开文档指向私有示例时，select_context 只能从已授权快照查找，不能越权补全。"""
    from app.auth import DEMO_READER

    add(pipeline, "guide", "alpha reference\n{* ../../docs_src/dependencies/example.py *}")
    code = code_document_id("docs_src/dependencies/example.py")
    add(pipeline, code, "alpha PRIVATE_CANARY_EXAMPLE", department="ops")
    snapshot = pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)
    anchor = RetrievalResult(snapshot.chunks[0].chunk, 1, dense_score=0.9)
    context, _ = select_context([anchor], snapshot, 0.35, "hybrid_rerank")
    assert all("PRIVATE_CANARY" not in r.chunk.text for r in context)


def test_exact_code_identifiers_work_without_semantic_anchor(pipeline):
    """英文模型没有高分时，显式 get_db/yield/finally 可找真实代码；仍然只用可见快照。"""
    from app.auth import DEMO_READER

    add(
        pipeline,
        "code.example",
        "def get_db():\n    try:\n        yield db\n    finally:\n        db.close()",
    )
    add(pipeline, "code.private", "def get_db():\n    PRIVATE_CANARY = 1", department="ops")
    snapshot = pipeline.catalog.snapshot(DEMO_READER, pipeline.embedder.fingerprint)
    context, trace = select_context(
        [], snapshot, 0.35, "hybrid_rerank", query="get_db yield finally"
    )
    assert context and context[0].chunk.source == "code.example"
    assert trace[0]["reason"] == "exact_identifier"
    assert not any("PRIVATE_CANARY" in r.chunk.text for r in context)


def test_review_detects_forbidden_uncited_context():
    """模型收到未引用的私有片段也应判越权；评测不能只检查最终回答和原始召回。"""
    case = {"expected_behavior": "abstain", "forbidden_documents": ["code.private"]}
    result = {
        "status": "abstained",
        "answer": "The evidence is insufficient.",
        "retrieved": [],
        "citations": [],
        "context": [{"chunk": {"source": "code.private"}}],
    }
    review = mechanical_review(case, result)
    assert review["forbidden_document_seen"] == ["code.private"]
    assert not review["boundary_pass"]


def test_server_repairs_once_and_counts_all_usage(monkeypatch):
    """真实 SDK 首轮收到未知 span ID，第二轮正确；次数固定两次且累计两轮 usage。"""
    requests = []

    def reply(request):
        """记录 SDK 消息并按轮次返回不同编号；这是协议测试，不冒充真实质量评测。"""
        payload = json.loads(request.content)
        requests.append(payload)
        span_id = 99 if len(requests) == 1 else 1
        content = {
            "language": "en",
            "claims": [
                {
                    "text": "Background tasks execute after the response.",
                    "evidence": [{"id": 1, "span_id": span_id}],
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(content)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
        )

    client = OpenAI(
        api_key="synthetic",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(reply)),
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: client)
    settings = Settings(
        llm_provider="compatible", llm_api_key=SecretStr("synthetic"), _env_file=None
    )
    result = Generator(settings).generate("When are background tasks executed?", evidence_result())
    assert result.status == "answered" and len(requests) == 2
    assert result.input_tokens == 100 and result.output_tokens == 40
    assert result.attempts[0]["failure_code"] == "SPAN_ID_OUT_OF_RANGE"
    assert "at most 6 claims" in requests[0]["messages"][0]["content"]
    assert len(requests[1]["messages"]) == 4


def test_claims_are_not_language_certificate(monkeypatch):
    """模型声明 en 但正文西班牙语时，两轮仍失败，系统不得显示为回答成功。"""
    calls = []

    def reply(request):
        """固定返回错误语言，验证纠正上限和不伪造成功。"""
        calls.append(request)
        content = {
            "language": "en",
            "claims": [
                {
                    "text": "Los procesos de trabajo se ejecutan de forma independiente "
                    "y no comparten la memoria.",
                    "evidence": [{"id": 1, "span_id": 1}],
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(content)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
        )

    client = OpenAI(
        api_key="synthetic",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(reply)),
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: client)
    result = Generator(
        Settings(llm_provider="compatible", llm_api_key=SecretStr("synthetic"), _env_file=None)
    ).generate("How do workers behave?", evidence_result())
    assert result.status == "abstained" and result.reason == "LANGUAGE_MISMATCH" and len(calls) == 2
