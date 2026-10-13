"""本机 HTTP 故障实验工具；只启动、停止当前脚本创建的子进程。"""

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread

import httpx

from app.config import PROJECT_ROOT


def free_port() -> int:
    """socket.bind 让系统选择临时端口；关闭探测 socket 后交给隔离测试服务使用。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def running_service(db_path, overrides=None):
    """Popen 启动独立服务并轮询 health；finally 只终止自己的进程，避免影响演示服务。"""
    port = free_port()
    env = dict(os.environ)
    env.update(
        {
            "RAG_DB_PATH": str(db_path),
            "RAG_PORT": str(port),
            "RAG_HOST": "127.0.0.1",
            "RAG_LLM_PROVIDER": "extractive",
            "RAG_LLM_API_KEY": "",
            "RAG_ALLOW_DEMO_AUTH": "true",
            "RAG_TOKENS_JSON": "",
            "HF_HUB_OFFLINE": "1",
            "RAG_MAX_CONCURRENT_QUERIES": "4",
        }
    )
    env.update(overrides or {})
    process = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("隔离服务启动失败")
                try:
                    if client.get(base + "/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("隔离服务启动超时")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@contextmanager
def fault_provider(actions):
    """ThreadingHTTPServer 提供真实本机 HTTP 超时/限流/恢复响应；不冒充真实大模型质量。"""
    state = {"requests": 0}
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        """供真实 SDK 访问的可控上游；请求参数不写日志。"""

        def log_message(self, *_args):
            """关闭默认访问日志，避免把测试 HTTP 内容写进报告。"""

        def do_POST(self):
            """读取 SDK 实际 JSON，按预设动作延迟、返回错误或合法证据，不自动重试。"""
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                index = state["requests"]
                state["requests"] += 1
            action = actions[min(index, len(actions) - 1)]
            if action == "timeout":
                time.sleep(0.4)
            if action in {"rate_limit", "server_error"}:
                code = 429 if action == "rate_limit" else 500
                reply = {"error": {"message": "injected failure", "type": "test_failure"}}
            else:
                context = json.loads(payload["messages"][1]["content"])["evidence"]
                quote = context[0]["spans"][0]["quote"][:200]
                code = 200
                content = {
                    "language": "en",
                    "claims": [{"text": quote, "evidence": [{"id": 1, "span_id": 1}]}],
                }
                reply = {
                    "id": "fault-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "synthetic-test-provider",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(content),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                }
            raw = json.dumps(reply).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass  # 真实 SDK 已超时并关闭连接，属于预期现象。

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
