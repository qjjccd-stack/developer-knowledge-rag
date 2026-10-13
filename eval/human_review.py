"""本地人工评分工作台：冻结来源、隐藏 AI 评分、校验人工输入并原子保存；不调用模型。"""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.config import PROJECT_ROOT

SCORE_FIELDS = (
    "correct",
    "complete",
    "all_claims_supported",
    "language_matches_question",
    "permission_respected",
)


class HumanScore(BaseModel):
    """只能提交明确的人工判断；任务成功由程序汇总，不能自报成功或审核身份类别。"""

    model_config = ConfigDict(extra="forbid")
    reviewer_name: str = Field(min_length=1, max_length=80)
    correct: StrictBool
    complete: StrictBool
    all_claims_supported: StrictBool | None
    language_matches_question: StrictBool
    permission_respected: StrictBool
    notes: str = Field(default="", max_length=4000)


def review_summary(rows: list[dict], scores: dict, role: str) -> dict:
    """按实际填写数量和完整任务标准计算比例；未审完时全量成功率为空，不把作者算第三方。"""
    reviewed = [scores[r["id"]] for r in rows if r["id"] in scores]
    full = len(reviewed) == len(rows)
    answered = [r for r in rows if r.get("status") == "answered"]
    supported = [scores[r["id"]] for r in answered if r["id"] in scores]
    successes = sum(s["task_success"] for s in reviewed)
    return {
        "total": len(rows),
        "reviewed": len(reviewed),
        "pending": len(rows) - len(reviewed),
        "fully_reviewed": full,
        "task_successes": successes,
        "task_success_rate_full_set": successes / len(rows) if full and rows else None,
        "task_success_rate_reviewed_subset": successes / len(reviewed) if reviewed else None,
        "supported_answer_rate": (
            sum(s["all_claims_supported"] for s in supported) / len(answered)
            if answered and len(supported) == len(answered)
            else None
        ),
        "author_reviewed": len(reviewed) if role == "author" else 0,
        "independent_third_party_reviewed": len(reviewed) if role == "external" else 0,
        "scope": "manual reviewer input; author review is not independent third-party annotation",
    }


def load_source_documents(dataset: dict) -> dict:
    """读取并核对固定语料摘要，加上明确标记的虚构评测资料，供人工展开完整原文。"""
    documents = {}
    for name in ("manifest.json", "code-examples.json"):
        manifest = json.loads((PROJECT_ROOT / "data/corpus" / name).read_text())
        for item in manifest["documents"]:
            raw = (PROJECT_ROOT / item["file"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("原文摘要与固定语料清单不一致")
            documents[item["doc_id"]] = {
                "text": raw.decode(),
                "source_url": item["source_url"],
                "title": item["title"],
                "sha256": item["sha256"],
            }
    for fixture in dataset.get("fixtures", []):
        documents[fixture["doc_id"]] = {
            "text": fixture["text"],
            "source_url": "",
            "title": fixture["title"],
            "synthetic_fixture": True,
        }
    return documents


class ReviewStore:
    """冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。"""

    def __init__(self, source: Path, output: Path, documents=None, role="author"):
        """核对完整报告、唯一 ID 与旧评分来源；恢复人工记录，首次建立全部待审核文件。"""
        if role not in {"author", "external"}:
            raise ValueError("审核类别无效")
        raw = source.read_bytes()
        report = json.loads(raw)
        rows = report["rows"]
        if not rows or len(rows) != report["requested"]:
            raise ValueError("评测尚未全部完成，不能建立全量审核")
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError("审核题目 ID 重复")
        if source.resolve() == output.resolve():
            raise ValueError("评分不能覆盖原始评测报告")
        self.source, self.output, self.role = source, output, role
        self.source_hash = hashlib.sha256(raw).hexdigest()
        self.report, self.rows = report, {r["id"]: r for r in rows}
        self.documents, self.lock = documents or {}, Lock()
        self.scores = {}
        self.created_at = datetime.now(UTC).isoformat()
        if output.is_file():
            existing = json.loads(output.read_text())
            if existing["source_report_sha256"] != self.source_hash:
                raise ValueError("评分来源已变化，请使用新的评分文件")
            if existing["reviewer_role"] != role:
                raise ValueError("旧评分身份类别不同，不能混合")
            for case_id, item in existing["scores"].items():
                if case_id not in self.rows:
                    raise ValueError("旧评分包含未知题目")
                payload = HumanScore.model_validate({k: item[k] for k in HumanScore.model_fields})
                self.scores[case_id] = self._record(case_id, payload, item["reviewed_at"])
            self.created_at = existing["created_at"]
        else:
            self._persist()

    def _check_source(self):
        """每次读取或保存前确认冻结报告未被修改，防止把评分绑定到另一批回答。"""
        if hashlib.sha256(self.source.read_bytes()).hexdigest() != self.source_hash:
            raise ValueError("原始报告已修改，请停止审核并重新建立来源")

    def _record(self, case_id: str, score: HumanScore, reviewed_at: str) -> dict:
        """校验适用性和失败备注；五项人工判断与程序状态边界共同决定完整任务成功。"""
        row = self.rows[case_id]
        data = score.model_dump()
        if not data["reviewer_name"].strip():
            raise ValueError("请填写审核者称呼")
        if row.get("status") == "answered" and data["all_claims_supported"] is None:
            raise ValueError("有回答的题目必须判断所有陈述是否有证据支持")
        if row.get("status") != "answered" and data["all_claims_supported"] is not None:
            raise ValueError("拒答或运行错误的引用支持项请选不适用")
        manual_pass = all(data[f] is not False for f in SCORE_FIELDS)
        boundary = row.get("mechanical_review", {}).get("boundary_pass", False)
        citations = row.get("mechanical_review", {}).get("citations_present_for_answer", False)
        passed = manual_pass and boundary and citations and row.get("status") != "error"
        if not passed and not data["notes"].strip():
            raise ValueError("未通过的题目请写明具体问题或不支持的陈述")
        return {
            **data,
            "task_success": passed,
            "automatic_boundary_pass": boundary,
            "reviewed_at": reviewed_at,
        }

    def _bundle(self):
        """生成带来源摘要、身份类别、逐题记录和正确分母的人工评分汇总。"""
        return {
            "schema_version": 1,
            "source_report": self.source.name,
            "source_report_sha256": self.source_hash,
            "dataset_sha256": self.report["dataset_sha256"],
            "model": self.report["model"],
            "reviewer_role": self.role,
            "created_at": self.created_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "summary": review_summary(list(self.rows.values()), self.scores, self.role),
            "scores": self.scores,
        }

    def _persist(self):
        """临时文件完成写入后 os.replace 原子替换评分；异常时清理临时文件。"""
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.output.parent,
                prefix=".human-review-",
                suffix=".json",
                delete=False,
            ) as file:
                temporary = Path(file.name)
                json.dump(self._bundle(), file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, self.output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def export(self):
        """加锁读取真实人工评分；检查来源，返回副本，避免调用者修改共享状态。"""
        with self.lock:
            self._check_source()
            return json.loads(json.dumps(self._bundle()))

    def save(self, case_id: str, score: HumanScore):
        """按唯一题号保存一次明确人工输入；写盘失败恢复旧记录，原报告始终不变。"""
        with self.lock:
            self._check_source()
            if case_id not in self.rows:
                raise KeyError(case_id)
            record = self._record(case_id, score, datetime.now(UTC).isoformat())
            previous = self.scores.get(case_id)
            self.scores[case_id] = record
            try:
                self._persist()
            except Exception:
                if previous is None:
                    self.scores.pop(case_id)
                else:
                    self.scores[case_id] = previous
                raise
            return json.loads(json.dumps(self._bundle()))

    def material(self):
        """仅展示原问题、回答、证据和人工记录，省略 AI 评分、通过提示与无效模型草稿。"""
        records = self.export()
        translation_path = self.source.with_name(self.source.stem + ".zh.json")
        translations = None
        if translation_path.is_file():
            translations = json.loads(translation_path.read_text())
            if translations["source_report_sha256"] != self.source_hash:
                raise ValueError("中文辅助材料与冻结报告来源不同")
        fields = (
            "id",
            "question",
            "category",
            "identity",
            "expected_behavior",
            "review_rubric",
            "answer",
            "status",
            "reason",
            "claims",
            "citations",
            "gold",
            "context",
            "forbidden_documents",
            "forbidden_strings",
            "answer_language",
        )
        return {
            "metadata": {k: v for k, v in records.items() if k != "scores"},
            "cases": [{k: row[k] for k in fields if k in row} for row in self.rows.values()],
            "scores": records["scores"],
            "source_documents": self.documents,
            "translations": translations,
        }


def create_review_app(store: ReviewStore, origin: str) -> FastAPI:
    """只为本机人工审核注册页面、读取、下载和保存接口，不调用检索或生成模型。"""
    app = FastAPI(title="RAG 人工复核", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def home():
        """返回人工评分页面；禁用跨域嵌入，页面不包含任何模型密钥。"""
        return HTMLResponse(
            (PROJECT_ROOT / "eval/review_ui.html").read_text(),
            headers={"X-Frame-Options": "DENY", "Cache-Control": "no-store"},
        )

    @app.get("/api/review")
    def material():
        """读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。"""
        try:
            return store.material()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/export")
    def export():
        """下载已经保存的真实人工评分，待审项不补写为成功。"""
        try:
            return JSONResponse(
                store.export(),
                headers={"Content-Disposition": f'attachment; filename="{store.output.name}"'},
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/review/{case_id}")
    def save(case_id: str, body: HumanScore, request: Request):
        """要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。"""
        if (
            request.headers.get("origin") != origin
            or request.headers.get("x-review-action") != "manual"
        ):
            raise HTTPException(403, "请从本机人工审核页面保存评分")
        try:
            return store.save(case_id, body)
        except KeyError as exc:
            raise HTTPException(404, "题目不存在") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return app
