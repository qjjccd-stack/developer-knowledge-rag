"""执行容量和上游故障的真实业务断言；测试替身不计入真实模型质量。"""

from threading import Event, Thread

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.rag.generation import GenerationUnavailable, Generator
from eval.run_answers import mechanical_review
from tests.test_boundaries import evidence_result


@pytest.mark.parametrize(
    "kind,code",
    [
        ("timeout", "UPSTREAM_TIMEOUT"),
        ("connect", "UPSTREAM_CONNECTION"),
        (429, "UPSTREAM_RATE_LIMIT"),
        (500, "UPSTREAM_ERROR"),
    ],
)
def test_sdk_fault_has_code_and_no_retry(monkeypatch, kind, code):
    """MockTransport 注入错误，真实 SDK 必须只请求一次且 Generator 转换稳定错误码。"""
    calls = []

    def reply(request):
        """记录调用次数，返回指定状态或抛出 HTTP 网络异常。"""
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout("injected", request=request)
        if kind == "connect":
            raise httpx.ConnectError("injected", request=request)
        return httpx.Response(kind, json={"error": {"message": "injected"}})

    client = OpenAI(
        api_key="synthetic",
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(reply)),
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: client)
    generator = Generator(
        Settings(llm_provider="compatible", llm_api_key=SecretStr("synthetic"), _env_file=None)
    )
    with pytest.raises(GenerationUnavailable) as caught:
        generator.generate("question", evidence_result())
    assert caught.value.code == code and len(calls) == 1


def test_failure_releases_capacity(pipeline):
    """首请求抛出超时后第二请求成功，证明 finally.release 不会永久占住执行名额。"""
    calls = []

    def query(*args):
        """首轮故障、下一轮恢复，验证接口会释放名额并如实回包。"""
        calls.append(args)
        if len(calls) == 1:
            raise GenerationUnavailable("UPSTREAM_TIMEOUT")
        return {"status": "answered"}

    pipeline.query = query
    pipeline.settings.max_concurrent_queries = 1
    with TestClient(create_app(pipeline.settings, pipeline)) as client:
        kwargs = {
            "headers": {"Authorization": "Bearer demo-reader-token"},
            "json": {"question": "alpha"},
        }
        first = client.post("/api/ask", **kwargs)
        assert first.status_code == 503 and first.json()["detail"]["code"] == "UPSTREAM_TIMEOUT"
        assert client.post("/api/ask", **kwargs).status_code == 200


def test_over_capacity_fails_fast(pipeline):
    """Event 持住首请求；第二请求返回 QUERY_CAPACITY，完成后新请求可以执行。"""
    entered, release = Event(), Event()

    def query(*_args):
        """仅用于占满测试名额；Event 通知主线程，不让等待超过两秒。"""
        entered.set()
        assert release.wait(2)
        return {"status": "answered"}

    pipeline.settings.max_concurrent_queries = 1
    pipeline.query = query
    with TestClient(create_app(pipeline.settings, pipeline)) as client:
        kwargs = {
            "headers": {"Authorization": "Bearer demo-reader-token"},
            "json": {"question": "alpha"},
        }
        thread = Thread(target=client.post, args=("/api/ask",), kwargs=kwargs)
        thread.start()
        try:
            assert entered.wait(2)
            busy = client.post("/api/ask", **kwargs)
            assert busy.status_code == 503 and busy.json()["detail"]["code"] == "QUERY_CAPACITY"
            assert busy.headers["Retry-After"] == "1"
        finally:
            release.set()
            thread.join(timeout=2)
        assert client.post("/api/ask", **kwargs).status_code == 200


def test_boundary_score_checks_retrieved_not_only_citations():
    """mechanical_review 即使未引用私有候选，也必须把越权检索判为失败。"""
    case = {"expected_behavior": "no_forbidden_evidence", "forbidden_documents": ["private"]}
    result = {
        "status": "answered",
        "answer": "safe looking",
        "citations": [{"source": "public"}],
        "retrieved": [{"chunk": {"source": "private"}}],
    }
    assert not mechanical_review(case, result)["boundary_pass"]
