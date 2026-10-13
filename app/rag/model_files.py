"""固定模型权重版本；有本地快照时不访问网络。"""

from pathlib import Path


def model_path(cache: Path, model: str, revision: str) -> str:
    """查找固定快照；缺失时 snapshot_download 下载该提交，而非滚动 main。"""
    repo = (
        "qdrant/all-MiniLM-L6-v2-onnx"
        if model == "sentence-transformers/all-MiniLM-L6-v2"
        else model
    )
    path = cache / ("models--" + repo.replace("/", "--")) / "snapshots" / revision
    model_file = path / ("model.onnx" if repo.startswith("qdrant/") else "onnx/model.onnx")
    needed = [
        model_file,
        path / "config.json",
        path / "tokenizer.json",
        path / "tokenizer_config.json",
        path / "special_tokens_map.json",
    ]
    if not all(p.is_file() for p in needed):
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo,
            revision=revision,
            cache_dir=str(cache),
            allow_patterns=["*.json", "model.onnx", "onnx/model.onnx"],
        )
    if not all(p.is_file() for p in needed):
        raise ValueError("固定版本模型文件不完整")
    return str(path)
