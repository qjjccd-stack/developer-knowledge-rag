"""下载固定版本的 MIT 官方技术资料，保留原文、许可证与 SHA256。"""

import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx

from app.config import PROJECT_ROOT

COMMIT = "f5c6e9b4f9cadc1bf0f9a1fd672e621206b63007"
PATHS = [
    "async.md",
    "tutorial/background-tasks.md",
    "tutorial/cors.md",
    "advanced/events.md",
    "tutorial/handling-errors.md",
    "tutorial/testing.md",
    "advanced/behind-a-proxy.md",
    "tutorial/security/oauth2-jwt.md",
    "tutorial/dependencies/index.md",
    "tutorial/dependencies/dependencies-with-yield.md",
    "deployment/server-workers.md",
    "deployment/docker.md",
    "advanced/testing-dependencies.md",
    "tutorial/middleware.md",
    "tutorial/response-model.md",
    "tutorial/body.md",
    "tutorial/query-params-str-validations.md",
    "tutorial/path-params-numeric-validations.md",
    "tutorial/metadata.md",
    "advanced/websockets.md",
]


def fetch_bytes(relative: str) -> bytes:
    """GitHub Contents API 下载固定提交；base64 解码并核对 Git Blob SHA1。"""
    url = f"https://api.github.com/repos/fastapi/fastapi/contents/{relative}"
    response = httpx.get(url, params={"ref": COMMIT}, timeout=20, trust_env=False)
    response.raise_for_status()
    metadata = response.json()
    raw = base64.b64decode(metadata["content"])
    blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
    if hashlib.sha1(blob).hexdigest() != metadata["sha"]:
        raise ValueError("Git Blob 校验失败")
    return raw


def fetch(path: str) -> dict:
    """httpx.get 下载固定提交中的文档；raise_for_status 拒绝失败；SHA256 标记原文。"""
    relative = "docs/en/docs/" + path
    url = f"https://raw.githubusercontent.com/fastapi/fastapi/{COMMIT}/{relative}"
    raw = fetch_bytes(relative)
    doc_id = path.removesuffix(".md").replace("/", ".")
    output = PROJECT_ROOT / "data" / "corpus" / (doc_id + ".md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    print(f"Fetched {doc_id}", flush=True)
    department = (
        "ops"
        if path
        in {"advanced/behind-a-proxy.md", "deployment/server-workers.md", "deployment/docker.md"}
        else "public"
    )
    return {
        "doc_id": doc_id,
        "file": str(output.relative_to(PROJECT_ROOT)),
        "title": raw.decode("utf-8").splitlines()[0].lstrip("# ").split(" {")[0],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "department": department,
        "source_url": f"https://github.com/fastapi/fastapi/blob/{COMMIT}/{relative}",
        "raw_url": url,
        "license": "MIT",
        "commit": COMMIT,
    }


def main() -> None:
    """ThreadPoolExecutor 下载文档，另存 LICENSE，再写可审计 manifest.json。"""
    with ThreadPoolExecutor(max_workers=4) as pool:
        documents = list(pool.map(fetch, PATHS))
    (PROJECT_ROOT / "data" / "corpus" / "LICENSE.fastapi").write_bytes(fetch_bytes("LICENSE"))
    manifest = {"downloaded_at": datetime.now(UTC).isoformat(), "documents": documents}
    (PROJECT_ROOT / "data" / "corpus" / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Downloaded {len(documents)} pinned MIT documents.")


if __name__ == "__main__":
    main()
