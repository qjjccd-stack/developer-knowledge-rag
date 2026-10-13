# 容器启动与数据保存

应用镜像保存源码、锁定依赖和种子文档。数据库与模型权重放在 `/var/lib/knowledge-rag` 持久卷中。
运行用户为 UID 10001；密钥和访问令牌在运行时注入，不打进镜像。Docker 健康检查只表示进程存活。

## 准备运行配置

在 `deploy/runtime.env` 保存以下配置。该文件已被 Git 和镜像构建忽略；自行生成足够长的令牌。

```dotenv
RAG_TOKENS_JSON={"替换成至少24字符的读者令牌":{"user_id":"reader","tenant_id":"demo","admin":false},"替换成至少24字符的管理员令牌":{"user_id":"admin","tenant_id":"demo","admin":true}}
RAG_LLM_PROVIDER=extractive
```

需要真实大模型时，另外配置 `RAG_LLM_PROVIDER=compatible`、`RAG_LLM_API_KEY`、`RAG_LLM_MODEL` 和 `RAG_LLM_BASE_URL`。
不要把密钥写在 README 或提交到仓库。默认本机端口为 8010，已有本地演示服务时请调整端口映射。

```bash
docker compose --env-file deploy/runtime.env build
docker compose --env-file deploy/runtime.env up -d
docker compose --env-file deploy/runtime.env exec rag python -m scripts.ingest --tenant demo
```

首次入库需要下载固定版本模型；后续启动复用持久卷中的模型缓存。入库的租户必须与令牌身份的 tenant_id 相同。
若使用 team1，则把命令中的 `--tenant demo` 改为 `--tenant team1`。重复执行会跳过未改变的文档。

## 重建容器

```bash
docker compose --env-file deploy/runtime.env down
docker compose --env-file deploy/runtime.env up -d
```

以上操作保留命名卷。原文、片段、版本和模型缓存会在新容器中继续使用。
`down -v` 会删除持久卷，仅在确定不需要其中的数据时使用。

## 自动验证

```bash
.venv/bin/python -m scripts.verify_container
```

脚本建立专用测试卷，入库真实模型资料，写入虚构测试文档，删除并重建容器，再检查原文版本和检索结果。
结束时只清理该脚本随机命名的测试容器和卷，不碰演示知识库。结果见 `reports/container-validation.json`。

## 本次实测环境

2026-10-11 使用 Lima 2.2.1 的临时 Ubuntu 26.04 ARM64 虚拟机、Docker 29.1.3 实际构建并运行容器，九项检查全部通过。验证使用 4 核、2GiB 内存；结束后清理测试容器和卷，并停止虚拟机。本机 8010 演示是独立的 Python 服务。

2026-10-12 修复引用、语言和上下文后重新构建并通过九项容器检查，记录在 `reports/container-repairs.json`。当前读者可见 19 份公共资料，运维身份可见 22 份；本机 HTTP 检查记录在 `reports/local-repair-smoke.json`。临时容器、测试卷已清理，虚拟机已停止。

Docker Hub 在当前网络中超时，本次改用 [Docker 官方在 AWS ECR 发布的镜像](https://www.docker.com/blog/news-from-aws-reinvent-docker-official-images-on-amazon-ecr-public/)，固定为：

```text
public.ecr.aws/docker/library/python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
```

需要同样的基础镜像时，在运行配置中增加 `RAG_BASE_IMAGE`。验证脚本也支持 `--base-image` 参数。镜像只构建在临时本机环境，未推送到任何远程镜像仓库。第一次网络失败保存在 reports/container-build-attempts.json 中，成功镜像摘要见 container-validation.json。

验证本机 Linux 容器能够运行，不能替代独立服务器或 amd64 平台的兼容性验证。
公网访问还需要 HTTPS、网关限流、备份恢复与正式身份系统；当前 compose 默认只绑定本机地址。
