ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
LABEL org.opencontainers.image.base.name=${BASE_IMAGE}
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
COPY eval ./eval
COPY scripts ./scripts
COPY data/corpus ./data/corpus
RUN pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home rag \
    && mkdir -p /var/lib/knowledge-rag/models \
    && chown -R rag:rag /var/lib/knowledge-rag
ENV RAG_HOST=0.0.0.0 RAG_PORT=8010 RAG_ALLOW_DEMO_AUTH=false \
    RAG_DB_PATH=/var/lib/knowledge-rag/catalog.sqlite3 \
    RAG_MODEL_CACHE=/var/lib/knowledge-rag/models
USER 10001:10001
# 令牌只在运行时注入；原文和模型权重持久化于外部卷。
EXPOSE 8010
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=2)"
CMD ["python", "-m", "app.main"]
