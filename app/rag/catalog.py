"""SQLite 保存原文、权限、版本与向量；事务防止留下半套索引。"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from urllib.parse import urlparse

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import Principal
from app.config import Settings
from app.rag.chunking import Chunk, chunk_text
from app.rag.store import VectorStore


class DocumentInput(BaseModel):
    """Pydantic 拒绝额外身份字段，校验 ID、原文长度和来源链接。"""

    model_config = ConfigDict(extra="forbid")
    doc_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=500_000)
    source_url: str = Field(default="", max_length=2000)
    department: str = Field(default="public", pattern=r"^[a-zA-Z0-9_-]{1,40}$")

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """str.strip 检查空白原文；不修改原文，保持行号。"""
        if not value.strip():
            raise ValueError("文档不能只有空白")
        return value

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        """urlparse 限制 HTTP(S) 来源；这里只保存链接，不访问该地址。"""
        parsed = urlparse(value)
        if value and (parsed.scheme not in {"https", "http"} or not parsed.netloc):
            raise ValueError("来源链接必须使用 HTTP(S)")
        return value


class Catalog:
    """文档目录；SQLite 并非向量数据库，当前小规模向量检索在内存执行。"""

    def __init__(self, settings: Settings):
        """mkdir 建目录，_connect 和 executescript 建表、外键及权限索引。"""
        self.settings = settings
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents(
                  tenant TEXT NOT NULL, doc_id TEXT NOT NULL, title TEXT NOT NULL,
                  text TEXT NOT NULL, source_url TEXT NOT NULL, department TEXT NOT NULL,
                  revision TEXT NOT NULL, PRIMARY KEY(tenant, doc_id));
                CREATE TABLE IF NOT EXISTS chunks(
                  tenant TEXT NOT NULL, doc_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                  payload TEXT NOT NULL, embedding BLOB NOT NULL,
                  PRIMARY KEY(tenant, doc_id, ordinal),
                  FOREIGN KEY(tenant, doc_id) REFERENCES documents(tenant, doc_id)
                    ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS documents_acl ON documents(tenant, department);
            """)

    @contextmanager
    def _connect(self):
        """connect 建独立连接；成功提交、异常回滚，finally 关闭连接。"""
        con = sqlite3.connect(self.settings.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _check_model(self, con, fingerprint: str) -> None:
        """execute 读取模型指纹；拒绝混合不同模型的向量。"""
        row = con.execute("SELECT value FROM meta WHERE key='model'").fetchone()
        if row and row[0] != fingerprint:
            raise ValueError("模型指纹变更：请使用新数据库路径重新入库")

    def upsert(self, document: DocumentInput, principal: Principal, embedder) -> dict:
        """chunk_text 分块、encode 算向量，BEGIN IMMEDIATE 原子替换；摘要相同则跳过。"""
        if not principal.admin:
            raise PermissionError("需要管理员身份")
        digest = hashlib.sha256(
            json.dumps(
                {
                    **document.model_dump(),
                    "model": embedder.fingerprint,
                    "chunking": [
                        "heading-lines-v1",
                        self.settings.chunk_size,
                        self.settings.chunk_overlap,
                    ],
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        with self._connect() as con:
            self._check_model(con, embedder.fingerprint)
            old = con.execute(
                "SELECT revision FROM documents WHERE tenant=? AND doc_id=?",
                (principal.tenant_id, document.doc_id),
            ).fetchone()
        previous = old[0] if old else None
        if previous == digest:
            return {"doc_id": document.doc_id, "status": "unchanged", "revision": digest}
        chunks = [
            replace(c, revision=digest, title=document.title, source_url=document.source_url)
            for c in chunk_text(
                document.text,
                document.doc_id,
                self.settings.chunk_size,
                self.settings.chunk_overlap,
            )
        ]
        embeddings = np.asarray(embedder.encode([c.text for c in chunks]), dtype=np.float32)
        if (
            embeddings.ndim != 2
            or len(embeddings) != len(chunks)
            or not len(chunks)
            or not np.isfinite(embeddings).all()
            or np.any(np.linalg.norm(embeddings, axis=1) < 1e-8)
        ):
            raise ValueError("模型返回无效向量，原版本保持可用")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._check_model(con, embedder.fingerprint)
            now = con.execute(
                "SELECT revision FROM documents WHERE tenant=? AND doc_id=?",
                (principal.tenant_id, document.doc_id),
            ).fetchone()
            current = now[0] if now else None
            if current == digest:
                return {"doc_id": document.doc_id, "status": "unchanged", "revision": digest}
            if current != previous:
                raise ValueError("文档被另一请求更新，请重新读取后提交")
            dim = con.execute("SELECT value FROM meta WHERE key='dimension'").fetchone()
            if dim and int(dim[0]) != embeddings.shape[1]:
                raise ValueError("向量维度与目录不一致")
            con.execute("INSERT OR IGNORE INTO meta VALUES('model',?)", (embedder.fingerprint,))
            con.execute(
                "INSERT OR IGNORE INTO meta VALUES('dimension',?)", (str(embeddings.shape[1]),)
            )
            con.execute(
                "DELETE FROM documents WHERE tenant=? AND doc_id=?",
                (principal.tenant_id, document.doc_id),
            )
            con.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                (
                    principal.tenant_id,
                    document.doc_id,
                    document.title,
                    document.text,
                    document.source_url,
                    document.department,
                    digest,
                ),
            )
            con.executemany(
                "INSERT INTO chunks VALUES(?,?,?,?,?)",
                [
                    (
                        principal.tenant_id,
                        document.doc_id,
                        c.index,
                        json.dumps(asdict(c), ensure_ascii=False),
                        vector.tobytes(),
                    )
                    for c, vector in zip(chunks, embeddings, strict=True)
                ],
            )
        return {
            "doc_id": document.doc_id,
            "status": "updated" if previous else "created",
            "revision": digest,
            "chunks": len(chunks),
        }

    def _scope(self, principal: Principal) -> tuple[str, list[str]]:
        """生成参数化权限条件；tenant 始终限制，管理员仅跳过部门过滤。"""
        if principal.admin:
            return "d.tenant=?", [principal.tenant_id]
        departments = ["public", *principal.departments]
        marks = ",".join("?" for _ in departments)
        return f"d.tenant=? AND d.department IN ({marks})", [principal.tenant_id, *departments]

    def snapshot(self, principal: Principal, fingerprint: str) -> VectorStore:
        """_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。"""
        scope, params = self._scope(principal)
        with self._connect() as con:
            con.execute("BEGIN")
            self._check_model(con, fingerprint)
            rows = con.execute(
                f"""SELECT c.payload,c.embedding FROM chunks c JOIN documents d
                ON d.tenant=c.tenant AND d.doc_id=c.doc_id WHERE {scope}
                ORDER BY c.doc_id,c.ordinal""",
                params,
            ).fetchall()
        store = VectorStore()
        if rows:
            store.add(
                [Chunk(**json.loads(row[0])) for row in rows],
                np.stack([np.frombuffer(row[1], dtype=np.float32) for row in rows]),
            )
        return store

    def documents(self, principal: Principal, doc_id: str | None = None) -> list[dict]:
        """_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。"""
        scope, params = self._scope(principal)
        columns = "d.doc_id,d.title,d.source_url,d.department,d.revision"
        if doc_id:
            scope += " AND d.doc_id=?"
            params.append(doc_id)
            columns += ",d.text"
        with self._connect() as con:
            return [
                dict(r)
                for r in con.execute(
                    f"SELECT {columns} FROM documents d WHERE {scope} ORDER BY d.doc_id", params
                )
            ]

    def delete(self, doc_id: str, principal: Principal) -> bool:
        """检查写权限，execute 删除租户内文档；外键同时清理旧片段。"""
        if not principal.admin:
            raise PermissionError("需要管理员身份")
        with self._connect() as con:
            cursor = con.execute(
                "DELETE FROM documents WHERE tenant=? AND doc_id=?", (principal.tenant_id, doc_id)
            )
            return cursor.rowcount > 0
