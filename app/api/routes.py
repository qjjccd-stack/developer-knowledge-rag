"""HTTP 边界：认证、范围校验和结构化错误，不接收客户端自报身份。"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.ui import HTML
from app.auth import Principal, authenticate, require_admin
from app.rag.catalog import DocumentInput
from app.rag.generation import GenerationUnavailable

router = APIRouter()
logger = logging.getLogger(__name__)
Identity = Annotated[Principal, Depends(authenticate)]


class AskRequest(BaseModel):
    """Pydantic 校验问题、模式、top_k；额外 tenant/admin 字段直接拒绝。"""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["dense", "bm25", "hybrid", "hybrid_rerank"] = "hybrid_rerank"
    top_k: int = Field(5, ge=1, le=10)
    answer_language: Literal["auto", "en", "zh"] = "auto"


@router.get("/", response_class=HTMLResponse)
def home():
    """HTMLResponse 显示独立问答页面；页面自身不含管理员令牌。"""
    return HTMLResponse(HTML)


@router.get("/health")
def health():
    """返回进程存活状态；不声称所有模型已加载或上游服务可用。"""
    return {"status": "alive"}


@router.post("/api/ask")
def ask(body: AskRequest, request: Request, principal: Identity):
    """authenticate 认证，acquire 限制并发；query 执行，finally 归还名额，故障分类回包。"""
    slots = request.app.state.query_slots
    if not slots.acquire(blocking=False):
        raise HTTPException(
            503,
            {"code": "QUERY_CAPACITY", "message": "服务繁忙，请稍后重试"},
            headers={"Retry-After": "1"},
        )
    try:
        return request.app.state.pipeline.query(
            body.question, principal, body.mode, body.top_k, body.answer_language
        )
    except GenerationUnavailable as exc:
        raise HTTPException(
            503,
            {"code": exc.code, "message": "生成服务暂时不可用，请稍后重试"},
            headers={"Retry-After": "1"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG request failed")
        raise HTTPException(503, "检索或生成暂时失败，请稍后重试") from exc
    finally:
        slots.release()


@router.get("/api/documents")
def documents(request: Request, principal: Identity):
    """Catalog.documents 只列出当前身份可见资料。"""
    return request.app.state.pipeline.catalog.documents(principal)


@router.get("/api/documents/{doc_id}")
def document(doc_id: str, request: Request, principal: Identity):
    """Catalog.documents 检查可见性；不可见或不存在统一返回 404。"""
    rows = request.app.state.pipeline.catalog.documents(principal, doc_id)
    if not rows:
        raise HTTPException(404, "文档不可用")
    return rows[0]


@router.post("/api/documents")
def upsert(body: DocumentInput, request: Request, principal: Identity):
    """require_admin 检查写权限，Catalog.upsert 事务入库；正文不能指定租户。"""
    require_admin(principal)
    pipeline = request.app.state.pipeline
    try:
        return pipeline.catalog.upsert(body, principal, pipeline.embedder)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        logger.exception("Document indexing failed")
        raise HTTPException(503, "入库失败，原文档版本保持可用") from exc


@router.delete("/api/documents/{doc_id}")
def delete(doc_id: str, request: Request, principal: Identity):
    """require_admin 校验权限，Catalog.delete 删除文档与片段。"""
    require_admin(principal)
    if not request.app.state.pipeline.catalog.delete(doc_id, principal):
        raise HTTPException(404, "文档不存在")
    return {"deleted": doc_id}
