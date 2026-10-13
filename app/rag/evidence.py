"""从已授权快照补充邻近说明和本地代码；引用原文由程序构造，保留真实文件及行号。"""

import re
from dataclasses import dataclass

from app.rag.retrieval import RetrievalResult, _tokenize


def technical_identifiers(query: str) -> set[str]:
    """提取显式代码标识符、驼峰 API 名及 yield/finally；普通词不触发额外召回。"""
    names = re.findall(
        r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b|"
        r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9]*\b|\byield\b|\bfinally\b",
        query,
    )
    return {name.lower() for name in names}


def code_document_id(path: str) -> str:
    """将固定 docs_src Python 示例路径转换为本地文档 ID；拒绝目录穿越与任意 URL。"""
    if not re.fullmatch(r"docs_src/[a-zA-Z0-9_/-]+\.py", path) or ".." in path:
        raise ValueError("代码示例路径无效")
    return "code." + path.removeprefix("docs_src/").removesuffix(".py").replace("/", ".")


def select_context(results, snapshot, min_score: float, mode: str, limit: int = 8, query=""):
    """先筛可靠锚点，再从同一权限快照添加其代码引用与相邻片段；记录每次选择原因。"""
    anchors = [
        r
        for r in results
        if (
            r.bm25_score is not None and r.bm25_score > 0
            if mode == "bm25"
            else r.dense_score is not None and r.dense_score >= min_score
        )
    ]
    context, decisions, seen = [], [], set()

    def add(result, reason, anchor=None):
        """按 chunk_id 去重并限制总数；附加来源不伪造向量分数，记录锚点 ID。"""
        chunk = result.chunk
        key = (chunk.source, chunk.index, chunk.revision)
        if key in seen or len(context) >= limit:
            return
        seen.add(key)
        context.append(result)
        decisions.append(
            {
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "lines": [chunk.start_line, chunk.end_line],
                "reason": reason,
                "anchor_chunk_id": anchor.chunk.chunk_id if anchor else None,
            }
        )

    identifiers = technical_identifiers(query)
    literal = []
    if identifiers:
        for item in snapshot.chunks:
            matches = identifiers & set(_tokenize(item.chunk.text))
            if matches:
                literal.append((len(matches), item.chunk))
    literal.sort(
        key=lambda pair: (
            -pair[0],
            not pair[1].source.startswith("code."),
            pair[1].source,
            pair[1].index,
        )
    )
    for _, chunk in literal[:2]:
        add(RetrievalResult(chunk, 0), "exact_identifier")
    for anchor in anchors:
        add(anchor, "relevance_anchor")
    # 只有前两个可靠锚点触发补充，防止所有历史文档无限进入上下文。
    expansion_anchors = list(context[:2]) if literal else anchors[:2]
    for anchor in expansion_anchors:
        paths = re.findall(r"\{\*\s+\.{2}/\.{2}/(docs_src/[a-zA-Z0-9_/-]+\.py)", anchor.chunk.text)
        for path in dict.fromkeys(paths):
            doc_id = code_document_id(path)
            for item in snapshot.chunks:
                if item.chunk.source == doc_id:
                    add(RetrievalResult(item.chunk, 0), "referenced_code", anchor)
    for anchor in expansion_anchors:
        neighbors = [
            item.chunk
            for item in snapshot.chunks
            if item.chunk.source == anchor.chunk.source
            and abs(item.chunk.index - anchor.chunk.index) == 1
        ]
        for chunk in sorted(neighbors, key=lambda c: c.index):
            add(RetrievalResult(chunk, 0), "adjacent_context", anchor)
    return context, decisions


@dataclass(frozen=True)
class EvidenceSpan:
    """程序控制的原文单元，编号只在当前请求对应片段内有效。"""

    span_id: int
    quote: str


def evidence_spans(text: str) -> list[EvidenceSpan]:
    """按空行及长度切出原文子串，不改写内容；剔除占位指令，单个引用不超过 800 字符。"""
    spans = []
    for paragraph in re.split(r"\n\s*\n", text):
        for start in range(0, len(paragraph), 800):
            quote = paragraph[start : start + 800].strip()
            if len(quote) < 15 or re.fullmatch(r"\{\*.*\*\}", quote):
                continue
            spans.append(EvidenceSpan(len(spans) + 1, quote))
    return spans
