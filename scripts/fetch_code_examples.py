"""补全两份固定版本官方示例；独立原文件保留实际代码行号，不改写 Markdown 来源。"""

import hashlib
import json

from app.config import PROJECT_ROOT
from app.rag.evidence import code_document_id
from scripts.fetch_corpus import COMMIT, fetch_bytes

EXAMPLES = (
    (
        "docs_src/dependencies/tutorial007_py310.py",
        "Database dependency with yield",
        ["tutorial.dependencies.dependencies-with-yield"],
    ),
    (
        "docs_src/app_testing/tutorial001_py310.py",
        "FastAPI TestClient complete example",
        ["tutorial.testing"],
    ),
)


def main() -> None:
    """fetch_bytes 校验 Git Blob；保存原始 Python 资料和 SHA256、来源、权限及引用关系。"""
    documents = []
    for relative, title, parents in EXAMPLES:
        raw = fetch_bytes(relative)
        doc_id = code_document_id(relative)
        path = PROJECT_ROOT / "data/corpus" / (doc_id + ".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        documents.append(
            {
                "doc_id": doc_id,
                "file": str(path.relative_to(PROJECT_ROOT)),
                "title": title,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "department": "public",
                "source_url": f"https://github.com/fastapi/fastapi/blob/{COMMIT}/{relative}",
                "commit": COMMIT,
                "license": "MIT",
                "referenced_by": parents,
            }
        )
        print(doc_id, "downloaded and verified", flush=True)
    (PROJECT_ROOT / "data/corpus/code-examples.json").write_text(
        json.dumps({"commit": COMMIT, "documents": documents}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
