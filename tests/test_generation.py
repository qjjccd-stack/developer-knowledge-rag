"""通过 HTTP 替身运行真实 SDK，验证生成接口与引用校验；不当作真实模型评测。"""

import json

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr

from app.config import Settings
from app.rag.generation import Generator
from tests.test_boundaries import evidence_result


@pytest.mark.parametrize(
    "content,status,reason",
    [
        (
            '{"language":"zh","claims":[{"text":"任务在响应后执行",'
            '"evidence":[{"id":1,"span_id":1}]}]}',
            "answered",
            "",
        ),
        (
            '{"language":"zh","claims":[{"text":"任务在响应后执行",'
            '"evidence":[{"id":1,"span_id":99}]}]}',
            "abstained",
            "INVALID_CITATION",
        ),
        ('{"language":"zh","claims":[]}', "abstained", "LLM_NO_EVIDENCE"),
        ("not JSON", "abstained", "INVALID_CITATION"),
    ],
)
def test_sdk_response_validation(monkeypatch, content, status, reason):
    """MockTransport 模拟模型响应；真实 SDK 解析，Generator 校验引用并保留真实 usage。"""

    def reply(request):
        """读取实际请求格式并返回符合服务商协议的响应。"""
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["messages"][0]["role"] == "system"
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
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
        )

    client = OpenAI(
        api_key="test-not-a-real-key",
        http_client=httpx.Client(transport=httpx.MockTransport(reply)),
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: client)
    settings = Settings(
        llm_provider="compatible",
        llm_api_key=SecretStr("test-only"),
        generation_max_attempts=1,
        _env_file=None,
    )
    result = Generator(settings).generate("任务什么时候运行？", evidence_result())
    assert (result.status, result.reason) == (status, reason)
    assert result.input_tokens == 50 and result.output_tokens == 20
    assert result.citations == ([1] if status == "answered" else [])
    if content == "not JSON":
        assert result.validation_failure == "INVALID_SCHEMA"
    if '"span_id":99' in content:
        assert result.validation_failure == "SPAN_ID_OUT_OF_RANGE"
