"""人工审核必须来自明确输入；所有评分测试仅用临时合成报告，不修改真实人工记录。"""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from eval.human_review import HumanScore, ReviewStore, create_review_app


def synthetic_score(**updates):
    """生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。"""
    return HumanScore(
        **{
            "reviewer_name": "Synthetic test reviewer",
            "correct": True,
            "complete": True,
            "all_claims_supported": True,
            "language_matches_question": True,
            "permission_respected": True,
            "notes": "Synthetic fixture only; not real annotation.",
            **updates,
        }
    )


def test_initial_scores_empty_and_ai_grades_hidden(review_paths):
    """初始化不把 AI 通过结论转成人工评分；全量成功率待填且来源原字节不变。"""
    source, output = review_paths
    original = source.read_bytes()
    store = ReviewStore(source, output)
    material = store.material()
    assert store.export()["scores"] == {}
    assert material["metadata"]["summary"]["task_success_rate_full_set"] is None
    assert material["metadata"]["summary"]["independent_third_party_reviewed"] == 0
    assert "DO_NOT_SHOW_AI_GRADE" not in json.dumps(material)
    assert "mechanical_review" not in material["cases"][0]
    assert source.read_bytes() == original


def test_saved_score_survives_restart_and_author_not_external(review_paths):
    """显式输入写盘后可恢复，作者计数与第三方计数分开；原评测报告保持不变。"""
    source, output = review_paths
    original = source.read_bytes()
    store = ReviewStore(source, output)
    saved = store.save("Q001", synthetic_score())
    assert saved["summary"]["reviewed"] == 1
    assert saved["summary"]["author_reviewed"] == 1
    assert saved["summary"]["independent_third_party_reviewed"] == 0
    assert saved["summary"]["task_success_rate_full_set"] == 1
    saved["scores"]["Q001"]["correct"] = False
    restored = ReviewStore(source, output).export()
    assert restored["scores"]["Q001"]["correct"] is True
    assert source.read_bytes() == original


def test_failure_requires_notes_and_remains_in_denominator(review_paths):
    """有未支持陈述必须保留具体原因，失败仍计入总数，不提高分数。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    with pytest.raises(ValueError, match="写明"):
        store.save("Q001", synthetic_score(all_claims_supported=False, notes=""))
    result = store.save(
        "Q001", synthetic_score(all_claims_supported=False, notes="Synthetic unsupported claim.")
    )
    assert result["summary"]["task_success_rate_full_set"] == 0
    assert result["summary"]["total"] == 1


@pytest.mark.parametrize("value", ["true", "false", 1])
def test_boolean_scores_not_coerced(value):
    """不把字符串或数字强制转换为人工通过；审核参数需要真实布尔值。"""
    with pytest.raises(ValidationError):
        synthetic_score(correct=value)


def test_support_not_applicable_only_for_no_answer(review_paths):
    """回答题必须判断支持关系，拒答允许不适用；字段适用性由真实状态决定。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    with pytest.raises(ValueError, match="必须判断"):
        store.save("Q001", synthetic_score(all_claims_supported=None))
    report = json.loads(source.read_text())
    report["rows"][0]["status"] = "abstained"
    source.write_text(json.dumps(report))
    output.unlink()
    store = ReviewStore(source, output)
    with pytest.raises(ValueError, match="不适用"):
        store.save("Q001", synthetic_score())
    assert store.save("Q001", synthetic_score(all_claims_supported=None))["scores"]["Q001"][
        "task_success"
    ]


def test_unknown_case_and_changed_source_cannot_save(review_paths):
    """非法题号和冻结来源变化都不能写入评分，不把旧评分绑定到新答案。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    original = output.read_bytes()
    with pytest.raises(KeyError):
        store.save("UNKNOWN", synthetic_score())
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="已修改"):
        store.save("Q001", synthetic_score())
    assert output.read_bytes() == original


def test_disk_failure_restores_unsaved_state(review_paths, monkeypatch):
    """模拟写盘失败，内存和文件都保持待审，不能向界面声称已经保存。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    original = output.read_bytes()

    def fail():
        """仅临时测试中的故障注入，不修改真实评分。"""
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(store, "_persist", fail)
    with pytest.raises(OSError):
        store.save("Q001", synthetic_score())
    assert store.export()["scores"] == {}
    assert output.read_bytes() == original


def test_origin_boundary_for_manual_save(review_paths):
    """跨网站和缺少手动操作头的请求拒绝；同源明确人工输入仅保存到临时评分文件。"""
    source, output = review_paths
    store = ReviewStore(source, output)
    client = TestClient(create_review_app(store, "http://127.0.0.1:8011"))
    payload = synthetic_score().model_dump()
    assert client.post("/api/review/Q001", json=payload).status_code == 403
    assert (
        client.post(
            "/api/review/Q001",
            json=payload,
            headers={"Origin": "http://example.org", "X-Review-Action": "manual"},
        ).status_code
        == 403
    )
    assert store.export()["scores"] == {}
    response = client.post(
        "/api/review/Q001",
        json=payload,
        headers={"Origin": "http://127.0.0.1:8011", "X-Review-Action": "manual"},
    )
    assert response.status_code == 200
    assert client.get("/api/export").json()["summary"]["reviewed"] == 1


def test_complete_scope_and_separate_output_required(review_paths):
    """没跑完不能建立全量审核，评分不能覆盖原报告，作者与第三方记录不能混用。"""
    source, output = review_paths
    with pytest.raises(ValueError, match="覆盖"):
        ReviewStore(source, source)
    store = ReviewStore(source, output)
    store.save("Q001", synthetic_score())
    with pytest.raises(ValueError, match="身份类别"):
        ReviewStore(source, output, role="external")
    report = json.loads(source.read_text())
    report["requested"] = 2
    source.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="尚未全部完成"):
        ReviewStore(source, output)


def test_manual_pass_cannot_override_execution_boundary(review_paths):
    """人工勾选不能掩盖模型越权或错误执行，完整任务成功还受实际边界条件约束。"""
    source, output = review_paths
    report = json.loads(source.read_text())
    report["rows"][0]["mechanical_review"]["boundary_pass"] = False
    source.write_text(json.dumps(report))
    store = ReviewStore(source, output)
    record = store.save("Q001", synthetic_score())
    assert record["summary"]["task_success_rate_full_set"] == 0
