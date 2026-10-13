"""中文仅是阅读层；所有翻译测试用合成数据，不调用模型或产生真实人工评分。"""

import json
from types import SimpleNamespace

import pytest

from eval.human_review import ReviewStore
from scripts.translate_review import collect_texts, is_code, translate_batch


def test_code_and_partial_docker_snippets_unchanged():
    """纯代码、URL 和半个 Docker 围栏不强制加中文；自然语言说明仍参加翻译。"""
    assert is_code('# (1)!\nCMD ["fastapi", "run", "app/main.py"]\n```')
    assert is_code("async def get_db():\n    yield db")
    assert is_code("* `http://localhost`\n* `https://localhost`")
    assert not is_code("Use `yield` and close the database in `finally`.")


def test_only_visible_claims_quotes_and_labels_translated():
    """去重陈述和证据；未校验草稿、AI 评分和人工评分不进入翻译输入。"""
    report = {
        "rows": [
            {
                "claims": [
                    {"text": "A supported claim.", "evidence": [{"quote": "Original passage."}]}
                ],
                "gold": [{"quote": "Original passage."}],
                "generation_diagnostics": [{"raw_draft": "DO_NOT_TRANSLATE"}],
                "assistant_review": {"notes": "DO_NOT_TRANSLATE"},
            }
        ]
    }
    assert collect_texts(report) == ["A supported claim.", "Original passage."]


def test_translation_ids_and_identifiers_checked():
    """首轮改动标识符会被拒，第二轮保留代码后接受；不是模型质量评测。"""
    calls = []

    def create(**kwargs):
        """合成翻译协议响应，明确记录两次请求，不读取真实密钥。"""
        calls.append(kwargs)
        value = "会话关闭。" if len(calls) == 1 else "调用 `db.close()` 关闭会话。"
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps({"translations": {"0": value}})),
                    finish_reason="stop",
                )
            ],
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    translated, attempts = translate_batch(client, "synthetic", ["Close using `db.close()`."])
    assert translated == {"Close using `db.close()`.": "调用 `db.close()` 关闭会话。"}
    assert len(calls) == len(attempts) == 2


def test_reading_translation_does_not_replace_evaluation_or_scores(review_paths):
    """中文显示材料单独加载，原英文和空人工记录都保持原字节与真实来源。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    original = source.read_bytes()
    source.with_name(source.stem + ".zh.json").write_text(
        json.dumps(
            {
                "source_report_sha256": store.source_hash,
                "questions": {"Q001": "合成测试问题？"},
                "texts": {"Synthetic response.": "合成测试回答。"},
                "complete": True,
            }
        )
    )
    material = store.material()
    assert material["translations"]["questions"]["Q001"] == "合成测试问题？"
    assert material["cases"][0]["question"] == "Synthetic question?"
    assert material["scores"] == {}
    assert source.read_bytes() == original


def test_translation_must_match_frozen_source(review_paths):
    """另一份报告的译文不能套到当前题目，以免审核错误的答案版本。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    source.with_name(source.stem + ".zh.json").write_text(
        json.dumps(
            {
                "source_report_sha256": "WRONG_SOURCE",
            }
        )
    )
    with pytest.raises(ValueError, match="来源不同"):
        store.material()
