"""保留上游分段接口，新增 Markdown 标题、原始行号与稳定片段 ID。"""

import hashlib
import re
from dataclasses import dataclass, replace

from app.config import Settings, get_settings


@dataclass(frozen=True)
class Chunk:
    """一个可追溯片段；source 是文档 ID，原始行号从 1 开始。"""

    text: str
    source: str
    index: int
    heading: str = ""
    start_line: int = 1
    end_line: int = 1
    revision: str = ""
    chunk_id: str = ""
    source_url: str = ""
    title: str = ""

    def __len__(self) -> int:
        """len(self.text) 返回字符数；不把字符数当作 Token 数。"""
        return len(self.text)


def chunk_text(
    text: str,
    source: str = "unknown",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。"""
    settings = get_settings()
    size = settings.chunk_size if chunk_size is None else chunk_size
    overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("要求 0 <= chunk_overlap < chunk_size")
    chunks: list[Chunk] = []
    buffer: list[tuple[int, str]] = []
    heading = ""
    in_fence = False

    def flush(keep_overlap: bool = False) -> None:
        """Chunk 输出缓冲区；len 控制保留的完整尾行，不跨标题重叠。"""
        nonlocal buffer
        body = "\n".join(line for _, line in buffer).strip()
        if body:
            chunks.append(Chunk(body, source, len(chunks), heading, buffer[0][0], buffer[-1][0]))
        tail: list[tuple[int, str]] = []
        if keep_overlap:
            for item in reversed(buffer):
                if len("\n".join(s for _, s in [item, *tail])) > overlap:
                    break
                tail.insert(0, item)
        buffer = tail

    for number, line in enumerate(text.splitlines(), 1):
        is_heading = not in_fence and bool(re.match(r"^#{1,6}\s", line))
        if is_heading:
            flush()
            heading = re.sub(r"\s*\{.*?\}\s*$", "", line.lstrip("# ")).strip()
        if line.lstrip().startswith(chr(96) * 3):
            in_fence = not in_fence
        for offset in range(0, max(len(line), 1), size):
            piece = line[offset : offset + size]
            if buffer and len("\n".join([*(s for _, s in buffer), piece])) > size:
                flush(True)
                if len("\n".join([*(s for _, s in buffer), piece])) > size:
                    buffer = []
            buffer.append((number, piece))
    flush()
    return [
        replace(
            c, chunk_id=hashlib.sha256(f"{source}:{c.index}:{c.text}".encode()).hexdigest()[:24]
        )
        for c in chunks
    ]


def chunk_documents(docs: list[tuple[str, str]], settings: Settings | None = None) -> list[Chunk]:
    """批量调用 chunk_text，保留各文档 source。"""
    settings = settings or get_settings()
    return [
        c
        for source, text in docs
        for c in chunk_text(text, source, settings.chunk_size, settings.chunk_overlap)
    ]
