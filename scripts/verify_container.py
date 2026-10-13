"""真实镜像、真实容器及持久卷验证；只清理本脚本创建的容器和卷。"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.config import PROJECT_ROOT


def docker_call(command: list[str], args: list[str], timeout=300) -> str:
    """subprocess.run 执行参数列表，避免 shell 拼接；错误不回显可能敏感的运行参数。"""
    result = subprocess.run(
        command + args, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout
    )
    if args[0] == "build":
        log = PROJECT_ROOT / ".container-runtime" / "build.log"
        log.parent.mkdir(exist_ok=True)
        log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        # build 命令没有密钥，可以在终端单独复查；报告只保存操作和退出码。
        raise RuntimeError(f"container operation {args[0]} failed: exit {result.returncode}")
    return result.stdout.strip()


def wait_health(base: str) -> None:
    """httpx 轮询进程存活，最多三十秒；模型可用性由随后真实问答验证。"""
    deadline = time.monotonic() + 30
    with httpx.Client(trust_env=False, timeout=2) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(base + "/health").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.2)
    raise RuntimeError("容器健康检查超时")


def main() -> None:
    """build 镜像，启动和入库，写测试文档，重建容器后验证原文/检索仍在，再清理测试卷。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker-command", nargs="+", default=["docker"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--image", default="developer-knowledge-rag:verified")
    parser.add_argument("--base-image", default="python:3.12-slim")
    parser.add_argument("--output", default="reports/container-validation.json")
    args = parser.parse_args()
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "status": "blocked",
        "checks": {},
        "scope": "local Linux container; not public deployment",
    }
    output = PROJECT_ROOT / args.output
    command = args.docker_command
    if not shutil.which(command[0]):
        report["reason"] = "CONTAINER_RUNTIME_UNAVAILABLE"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit("未找到容器命令，不能声称完成了容器验证")
    suffix = secrets.token_hex(4)
    volume, name = f"rag-verify-data-{suffix}", f"rag-verify-{suffix}"
    containers = []
    volume_created = False
    started = time.monotonic()
    try:
        report["runtime_version"] = docker_call(
            command, ["version", "--format", "{{.Server.Version}}"]
        )
        if not args.skip_build:
            docker_call(
                command,
                ["build", "--tag", args.image, "--build-arg", "BASE_IMAGE=" + args.base_image, "."],
                timeout=1200,
            )
        report["base_image"] = args.base_image
        report["image_id"] = docker_call(
            command, ["image", "inspect", args.image, "--format", "{{.Id}}"]
        )
        report["architecture"] = docker_call(
            command, ["image", "inspect", args.image, "--format", "{{.Architecture}}"]
        )
        report["checks"]["image_build"] = True
        docker_call(command, ["volume", "create", volume])
        volume_created = True
        admin, reader = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        private_dir = PROJECT_ROOT / ".container-runtime"
        private_dir.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix="rag-container-env-", dir=private_dir) as temp:
            env_file = Path(temp) / "runtime.env"
            mapping = {
                admin: {"user_id": "verify-admin", "tenant_id": "demo", "admin": True},
                reader: {"user_id": "verify-reader", "tenant_id": "demo"},
            }
            env_file.write_text("RAG_TOKENS_JSON=" + json.dumps(mapping) + "\nHF_HUB_OFFLINE=1\n")
            os.chmod(env_file, 0o600)

            def start_container(container_name):
                """run 创建专用容器，inspect 只读取映射端口，绝不输出容器密钥环境变量。"""
                docker_call(
                    command,
                    [
                        "run",
                        "-d",
                        "--name",
                        container_name,
                        "--env-file",
                        str(env_file),
                        "--mount",
                        f"source={volume},target=/var/lib/knowledge-rag",
                        "-p",
                        "127.0.0.1::8010",
                        args.image,
                    ],
                )
                containers.append(container_name)
                ports = json.loads(
                    docker_call(
                        command,
                        ["inspect", container_name, "--format", "{{json .NetworkSettings.Ports}}"],
                    )
                )["8010/tcp"]
                base = "http://127.0.0.1:" + ports[0]["HostPort"]
                wait_health(base)
                return base

            base = start_container(name)
            cache = PROJECT_ROOT / "data/models"
            if not cache.is_dir():
                raise RuntimeError("请先下载固定版本的本地模型，用于离线容器测试")
            docker_call(
                command,
                ["cp", str(cache) + "/.", name + ":/var/lib/knowledge-rag/models"],
                timeout=300,
            )
            docker_call(command, ["exec", name, "python", "-m", "scripts.ingest"], timeout=300)
            report["checks"]["non_root"] = (
                docker_call(command, ["exec", name, "id", "-u"]) == "10001"
            )
            report["checks"]["no_project_env_in_image"] = (
                docker_call(
                    command,
                    [
                        "exec",
                        name,
                        "python",
                        "-c",
                        "from pathlib import Path; print(not Path('/app/.env').exists())",
                    ],
                )
                == "True"
            )
            headers = {"Authorization": "Bearer " + reader}
            admin_headers = {"Authorization": "Bearer " + admin}
            with httpx.Client(trust_env=False, timeout=60) as client:
                listed = client.get(base + "/api/documents", headers=headers)
                base_manifest = json.loads((PROJECT_ROOT / "data/corpus/manifest.json").read_text())
                supplements = PROJECT_ROOT / "data/corpus/code-examples.json"
                entries = base_manifest["documents"]
                if supplements.is_file():
                    entries = entries + json.loads(supplements.read_text())["documents"]
                expected_public = sum(d["department"] == "public" for d in entries)
                report["checks"]["reader_scope"] = (
                    listed.status_code == 200
                    and len(listed.json()) == expected_public
                    and all(d["department"] == "public" for d in listed.json())
                )
                report["reader_visible_documents"] = len(listed.json())
                question = (
                    "When should I use Celery rather than BackgroundTasks for heavy computation?"
                )
                asked = client.post(base + "/api/ask", headers=headers, json={"question": question})
                report["checks"]["real_model_query"] = asked.status_code == 200 and bool(
                    asked.json().get("citations")
                )
                doc_id = "container-persistence-capsule"
                marker = "PERSISTENCE_CAPSULE_7429"
                document = {
                    "doc_id": doc_id,
                    "title": "Container persistence capsule",
                    "text": "# Container persistence capsule\n"
                    + "The container persistence capsule marker is "
                    + marker
                    + ".",
                }
                written = client.post(base + "/api/documents", headers=admin_headers, json=document)
                written.raise_for_status()
                revision = written.json()["revision"]
                report["checks"]["write_then_read"] = (
                    marker
                    in client.get(base + "/api/documents/" + doc_id, headers=headers).json()["text"]
                )
            docker_call(command, ["rm", "-f", name])
            containers.remove(name)
            base = start_container(name + "-recreated")
            with httpx.Client(trust_env=False, timeout=60) as client:
                restored = client.get(base + "/api/documents/" + doc_id, headers=headers)
                report["checks"]["survives_container_recreation"] = (
                    restored.status_code == 200
                    and restored.json()["revision"] == revision
                    and marker in restored.json()["text"]
                )
                found = client.post(
                    base + "/api/ask",
                    headers=headers,
                    json={
                        "question": "What is the container persistence capsule marker?",
                        "mode": "bm25",
                    },
                )
                report["checks"]["restored_document_retrievable"] = (
                    found.status_code == 200
                    and any(c["source"] == doc_id for c in found.json()["citations"])
                )
                deleted = client.delete(base + "/api/documents/" + doc_id, headers=admin_headers)
                report["checks"]["delete_after_recreation"] = (
                    deleted.status_code == 200
                    and client.get(base + "/api/documents/" + doc_id, headers=headers).status_code
                    == 404
                )
        report["status"] = "passed" if all(report["checks"].values()) else "failed"
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        if isinstance(exc, RuntimeError):
            report["error_message"] = str(exc)
        print("Container verification failed:", type(exc).__name__, flush=True)
    finally:
        for container in containers:
            docker_call(command, ["rm", "-f", container])
        if volume_created:
            docker_call(command, ["volume", "rm", volume])
        report["duration_seconds"] = time.monotonic() - started
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report["checks"]}), flush=True)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
