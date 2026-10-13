"""验证原文摘要后增量入库；默认只写独立 RAG 的数据库。"""

import argparse
import hashlib
import json
import re

from app.auth import Principal
from app.config import PROJECT_ROOT
from app.rag.catalog import DocumentInput
from app.rag.pipeline import RAGPipeline


def main() -> None:
    """解析目标租户，读取 manifest；SHA256 校验原文；Catalog.upsert 原子入库。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="demo")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}", args.tenant):
        parser.error("tenant 须为 1 至 100 个字母、数字、点、横线或下划线")
    principal = Principal("corpus-importer", args.tenant, (), True)
    manifest = json.loads((PROJECT_ROOT / "data" / "corpus" / "manifest.json").read_text())
    supplemental = PROJECT_ROOT / "data/corpus/code-examples.json"
    if supplemental.is_file():
        manifest["documents"].extend(json.loads(supplemental.read_text())["documents"])
    pipeline = RAGPipeline()
    counts = {}
    for item in manifest["documents"]:
        raw = (PROJECT_ROOT / item["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError(f"原文摘要不一致：{item['doc_id']}")
        doc = DocumentInput(
            doc_id=item["doc_id"],
            title=item["title"],
            text=raw.decode("utf-8"),
            source_url=item["source_url"],
            department=item["department"],
        )
        result = pipeline.catalog.upsert(doc, principal, pipeline.embedder)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        print(doc.doc_id, result["status"], flush=True)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
