# 研发／运维知识库 RAG

基于 [Pasukalu/rag-qa-system](https://github.com/Pasukalu/rag-qa-system) 的开源改造项目，保留分块、向量检索、BM25、RRF、Cross-Encoder 和 FastAPI 的整体结构，补充版本管理、权限过滤、引用校验与可复现评测。定位是可以学习、演示和量化比较的小规模研发知识库。

上游版本：9dd2eb16bfeeb9f483b87490805ed18cdd5bc979。原 MIT LICENSE、原 README 和文件摘要均保留。不要把上游已有的混合检索算法说成独立原创。

## 本次改造

| 内容 | 解决的实际问题 |
|---|---|
| 标题分块与行号、版本、稳定 ID | 找到资料后还能指出具体章节和原文位置 |
| SQLite 增量目录与事务替换 | 相同资料不重复算向量；更新、删除后旧片段不再可检索 |
| 服务端身份与检索前权限过滤 | 不可见文档不进入向量、BM25 或重排候选 |
| 编号引用与程序还原 | 模型选择片段／原文单元编号，程序保留真实摘录，避免复制时改动 Markdown |
| 授权上下文补全与语言检查 | 补齐相邻说明和本地代码；语言或格式错误最多纠正一次 |
| 请求隔离与阶段计时 | top_k、结果和消耗属于本次请求，不修改共享配置 |
| 四种检索方案对照 | 用真实模型、具体答案段落标注，比较效果和耗时 |

已有 20 篇固定版本的 FastAPI 官方英文文档，以及本次补充的 2 份同版本代码示例，合计 22 份资料、325 个片段。MIT 许可证保存在 data/corpus/LICENSE.fastapi。运维文档的权限分类是模拟的；所有种子资料本身均为公开资料。

默认英文模型：all-MiniLM-L6-v2（384 维）与 ms-marco-MiniLM-L-6-v2。固定权重提交，FastEmbed / ONNX 本地运行。生成层支持中文／英文，已验证 4 道含明确技术标识符的中文题；尚未系统验证中文语义检索。

## 启动

本机已创建独立 .venv、下载模型并完成入库。在本目录运行：

~~~bash
.venv/bin/python -m app.main
~~~

访问 http://127.0.0.1:8010/。页面默认读者令牌 demo-reader-token，只能看到 19 份公共资料；demo-ops-token 可额外读取 3 篇模拟运维资料。管理员令牌 demo-admin-token 用于 API 写入和管理。令牌只保存在当前页面输入框中。

在新机器上：

~~~bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m scripts.ingest
.venv/bin/python -m app.main
~~~

模型首次下载需要网络，之后可设置 HF_HUB_OFFLINE=1；文档已随源码保存，不必重新联网抓取。网络无法访问 Hugging Face 时可自行选择镜像设置 HF_ENDPOINT，代码不强制更改系统代理。

## 开启生成回答

默认是 **资料摘录模式**：真实检索和重排，但不调用生成模型、不产生付费 Token。页面展示检索能力，生成质量以单独的真实模型评测报告为准。

复制 .env.example 为本目录 .env，设置：

~~~dotenv
RAG_LLM_PROVIDER=compatible
RAG_LLM_API_KEY=填写自己的密钥
RAG_LLM_BASE_URL=https://api.deepseek.com
RAG_LLM_MODEL=deepseek-chat
~~~

重启服务后，模型输出陈述与证据编号，程序还原原文摘录并检查引用和正文语言，再显示结果。格式、编号或语言失败时最多纠正一次，网络故障不自动重试。服务商返回的真实 Token 累计记录；未配置价格时费用为空。常规服务只读取本项目配置。评测可在得到授权后使用 --reuse-ticket-config 临时读取工单配置，不复制或打印密钥。

引用校验保证的是 **ID 和摘录真实存在**，不能证明答案陈述必然被原文语义支持。真实生成的正确性与忠实度仍需人工按证据复核。模型/服务商可自行替换，首次替换后需重新验证协议和回答质量。

## 评测与实测数据

~~~bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m eval.run_eval --repeat 3
# 配置真实生成模型后才运行：
.venv/bin/python -m eval.run_answers --limit 5
.venv/bin/python -m eval.run_stability
# 使用真实生成配置，或者在明确授权后附加 --reuse-ticket-config：
.venv/bin/python -m eval.run_live_stability
# 容器环境可用时：
.venv/bin/python -m scripts.verify_container
~~~

以下是 2026-10-12 对当前 22 份资料／325 个片段的全量检索对照。32 条开发集问题，每条标签包含文档 ID + 原文摘录。四方案各重复 3 次，共 384 次检索运行；独立问题仍是 32 条。新记录见 reports/retrieval-comparison-full-20261012.json；原 20 篇／323 片段的历史基线仍保留在 reports/retrieval-comparison.json。

| 方案 | 证据覆盖率@5 | 找齐全部标注@5 | MRR@5 | 平均耗时 |
|---|---:|---:|---:|---:|
| 向量 | 85.94% | 84.38% | 0.601 | 25.5 ms |
| BM25 | 93.75% | 90.63% | 0.759 | 21.3 ms |
| 混合 RRF | 90.63% | 87.50% | 0.728 | 25.4 ms |
| 混合 + 重排 | 89.06% | 87.50% | 0.810 | 1252.2 ms |

在这批术语较多的文档上，BM25 的覆盖率最好；重排的首个正确片段排名最好，但延迟明显增加。数据来自本机 ARM CPU、热模型、小规模人工整理的开发集，**不是盲测、并发压测或线上 SLA**。测试集未用于修改参数追求满分，但题目由同一开发过程选择，仍可能有样本偏差。

新增人工审核保存、来源冻结、真假评分和失败分母测试后，离线测试共 76 项通过。它们验证权限、更新/删除、无效向量、编号引用、语言、有限纠正、真实 SDK 协议、并发参数隔离、执行容量与错误后的名额释放。权限评测还检查真正送给模型但没有被引用的上下文。单元测试的 SDK 响应由 HTTP 替身提供。

历史基线使用 deepseek-chat 完成 50 题端到端评测与 6 道相近主题无答案题。按证据逐题进行的助手复核中，主评测 43/50 达到完整任务要求；未通过项包括证据漏召回、引用校验失败、回答不完整及语言错误。

修复后七个失败场景每题两轮回归，14/14 达到完整任务要求；另有十二道开发验证题，8 道中英文问答与 4 道无答案／权限题均达到预期。原因和中间版本见 docs/answer-repairs.md。

随后已用修复版重新运行全部 50 题：39 题回答、11 题拒答、运行错误 0；自动状态／权限检查 50/50，39 个回答的语言检查匹配。原始记录见 reports/answer-review-full-20261012.json。它是执行与机械检查结果，完整正确率仍待人工内容复核。

人工复核工作台运行于 http://127.0.0.1:8011/，默认提供中文辅助阅读和可展开的原始英文。每题五项评分，点击保存后持久记录；评分没有预填。当前采用作者人工复核，不能称为第三方独立标注。完整操作见 docs/manual-review-guide.md；全量比例仅在所有题目评分后生成。

本次检索对照和真实生成评测在同一台机器上部分重叠执行；排序指标基于固定快照，耗时不是隔离性能基准。

本机 1/2/4 并发的 36 次资料摘录请求及 12 次真实生成热请求均无运行失败；真实生成 4 并发的 P95 为 3.75 秒，仅有四条样本。超时、429、500 与随后恢复使用真实本机 HTTP 和 SDK 验证，不冒充真实上游故障率。完整记录与逐题引用见 docs/validation-results.md。

## 阅读顺序

1. docs/upstream-and-changes.md：选仓库依据及自己与上游的贡献边界。
2. app/rag/pipeline.py：把检索、重排和回答串起来的总入口。
3. app/rag/catalog.py：原文、向量、版本和权限怎样持久化。
4. app/rag/retrieval.py：向量、BM25、RRF 怎样排名。
5. app/rag/generation.py：模型怎样收到证据，程序怎样核验引用。
   app/rag/evidence.py 与 app/rag/language.py：怎样补齐授权上下文，以及检查回答语言。
6. app/auth.py 与 app/api/routes.py：HTTP 身份、参数和权限边界。
7. eval/tech_qa.json 与 eval/run_eval.py：成功标准、标签和对照实验。
8. docs/functions.md：每个函数的功能，以及里面调用的函数说明。
9. docs/validation-results.md：真实问答结果、失败案例、并发与容器验证。
10. docs/deployment.md：容器启动、访问令牌、租户入库和持久卷。
11. docs/answer-repairs.md：本次失败怎样复现、定位、修复，以及验证数字的范围。
12. docs/full-evaluation-20261012.md 与 docs/manual-review-guide.md：修复版全量结果，以及如何逐题填写真实人工评分。

## 工作流

~~~mermaid
flowchart LR
  A[技术文档] --> B[摘要检查与标题分块]
  B --> C[本地语义向量]
  C --> D[(SQLite 原文与版本)]
  U[用户问题 + 访问令牌] --> I[服务端识别身份]
  I --> P[SQL 筛选可见片段]
  D --> P
  P --> H[向量 / BM25 / 混合召回]
  H --> R[可选 Cross-Encoder 重排]
  R --> C2[补齐授权代码与相邻证据]
  C2 --> E[资料摘录或 LLM 选择编号并生成]
  E --> V[还原原文并检查引用与语言]
  V --> O[回答 + 来源 + 行号]
  V --> F[证据不足时拒答]
~~~

## HTTP 与部署边界

GET /health 只表示进程存活。问答、文档列表和原文需要 Authorization: Bearer 令牌；POST /api/documents、DELETE /api/documents/{doc_id} 需要管理员身份。客户端不能在正文传 admin 或 tenant。来源 URL 只保存为元数据，服务端不访问客户端提供的地址。

已在临时 Linux ARM64 环境实际构建镜像并通过九项容器检查：普通用户运行、项目配置不进镜像、读者范围、真实向量与重排模型的资料摘录问答、写入读取、容器重建后的原文/版本/检索保存，以及重建后删除。修复版也重新构建并通过同样九项检查，记录在 reports/container-repairs.json。该历史报告的 `real_model_query` 字段指检索模型运行，容器检查没有配置生成模型密钥，不能据此宣称已在容器内验证真实大模型生成；真实生成结果来自上述单独的问答评测。Dockerfile 使用锁定依赖，compose.yaml 挂载持久卷；完整步骤见 docs/deployment.md。使用 AWS ECR 的 Docker 官方 Python 镜像并固定内容摘要。

尚未公网部署，也未验证另一台物理服务器或 amd64 平台。公开部署需配置 HTTPS、网关限流、备份恢复及正式身份系统。当前是小语料内存检索，未实施大规模 ANN、OCR、所有 Markdown 代码 include 的自动补全或完整多语检索质量验证。这些是后续工作，不能写成已交付成果。

requirements.lock.txt 锁定本次验证的依赖版本。本次首次上传不包含 GitHub Actions 工作流；测试和部署可按上面的命令手动运行。

可用简历描述与面试追问见 docs/resume-project.md。
