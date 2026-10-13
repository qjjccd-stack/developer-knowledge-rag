"""独立 FastAPI 服务；每个应用实例拥有自己的身份映射和流水线。"""

from threading import BoundedSemaphore

from fastapi import FastAPI

from app.api.routes import router
from app.auth import token_map
from app.config import Settings, get_settings
from app.rag.pipeline import RAGPipeline


def create_app(settings: Settings | None = None, pipeline=None) -> FastAPI:
    """token_map 校验认证配置，RAGPipeline 初始化目录，include_router 注册接口。"""
    settings = settings or get_settings()
    app = FastAPI(title="研发知识库 RAG", version="0.2.0")
    app.state.tokens = token_map(settings)
    app.state.pipeline = pipeline or RAGPipeline(settings)
    app.state.query_slots = BoundedSemaphore(settings.max_concurrent_queries)
    app.include_router(router)
    return app


def run() -> None:
    """get_settings 读取地址，uvicorn.run 启动服务；默认只允许本机访问。"""
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
