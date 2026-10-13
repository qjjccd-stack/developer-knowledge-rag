"""启动仅本机可见的五十题人工复核工作台；不调用付费模型，不自动生成评分。"""

import argparse
import hashlib
import json

from app.config import PROJECT_ROOT
from eval.human_review import ReviewStore, create_review_app, load_source_documents


def main():
    """读取冻结报告及固定原文，建立 ReviewStore，使用 uvicorn 启动本机人工审核。"""
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="reports/answer-review-full-20261012.json")
    parser.add_argument("--dataset", default="eval/answer_cases.json")
    parser.add_argument("--output", default="reports/human-review-full-20261012.json")
    parser.add_argument("--role", choices=("author", "external"), default="author")
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("端口必须在 1024 到 65535 之间")
    dataset_raw = (PROJECT_ROOT / args.dataset).read_bytes()
    dataset = json.loads(dataset_raw)
    report = json.loads((PROJECT_ROOT / args.report).read_text())
    if hashlib.sha256(dataset_raw).hexdigest() != report["dataset_sha256"]:
        parser.error("审核资料集与冻结评测报告不一致")
    store = ReviewStore(
        PROJECT_ROOT / args.report,
        PROJECT_ROOT / args.output,
        load_source_documents(dataset),
        args.role,
    )
    origin = f"http://127.0.0.1:{args.port}"
    print(f"人工复核地址：{origin}；评分自动保存于 {args.output}", flush=True)
    uvicorn.run(create_review_app(store, origin), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
