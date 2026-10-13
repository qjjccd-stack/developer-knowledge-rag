# 函数功能与内部调用说明

先读 pipeline → catalog → retrieval → generation，再看 HTTP 接口与评测。
以下从源码生成。类的 dataclass / Pydantic 初始化函数由框架自动生成。
函数内部调用包括内置函数和内部小函数；SQL 操作的职责也在源码注释中说明。

## app/api/routes.py

### home（第 31 行）

HTMLResponse 显示独立问答页面；页面自身不含管理员令牌。

内部使用：

- `HTMLResponse()`：返回静态问答界面
- `router.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### health（第 37 行）

返回进程存活状态；不声称所有模型已加载或上游服务可用。

内部使用：

- `router.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### ask（第 43 行）

authenticate 认证，acquire 限制并发；query 执行，finally 归还名额，故障分类回包。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `logger.exception()`：记录失败堆栈便于定位
- `request.app.state.pipeline.query()`：仅用于占满测试名额；Event 通知主线程，不让等待超过两秒。
- `router.post()`：发送测试 POST 请求
- `slots.acquire()`：非阻塞申请一个问答执行名额；名额满时接口立即返回繁忙
- `slots.release()`：归还问答名额；成功或异常都在 finally 中执行
- `str()`：转换路径或错误信息为字符串

### documents（第 72 行）

Catalog.documents 只列出当前身份可见资料。

内部使用：

- `request.app.state.pipeline.catalog.documents()`：_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。
- `router.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### document（第 78 行）

Catalog.documents 检查可见性；不可见或不存在统一返回 404。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `request.app.state.pipeline.catalog.documents()`：_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。
- `router.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### upsert（第 87 行）

require_admin 检查写权限，Catalog.upsert 事务入库；正文不能指定租户。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `logger.exception()`：记录失败堆栈便于定位
- `pipeline.catalog.upsert()`：chunk_text 分块、encode 算向量，BEGIN IMMEDIATE 原子替换；摘要相同则跳过。
- `require_admin()`：检查已认证身份的写权限；无权限抛出 HTTPException(403)。
- `router.post()`：发送测试 POST 请求
- `str()`：转换路径或错误信息为字符串

### delete（第 101 行）

require_admin 校验权限，Catalog.delete 删除文档与片段。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `request.app.state.pipeline.catalog.delete()`：检查写权限，execute 删除租户内文档；外键同时清理旧片段。
- `require_admin()`：检查已认证身份的写权限；无权限抛出 HTTPException(403)。
- `router.delete()`：检查写权限，execute 删除租户内文档；外键同时清理旧片段。

## app/auth.py

### token_map（第 26 行）

json.loads 解析服务端令牌配置；Principal 固定对应权限。

内部使用：

- `Principal()`：构造对象：可信身份；dataclass 自动初始化，不从问答正文构造。
- `ValueError()`：表示输入或数据不符合约束
- `isinstance()`：检查配置对象类型
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `mapping.items()`：遍历映射键值
- `settings.tokens_json.get_secret_value()`：只在必要调用时取得配置值，不输出密钥

### authenticate（第 48 行）

从 Authorization 查身份；compare_digest 比较令牌；失败返回 401。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `expected.encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `header.startswith()`：检查协议、标题或围栏前缀
- `request.app.state.tokens.items()`：遍历映射键值
- `request.headers.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `secrets.compare_digest()`：以恒定时间方式比较服务端令牌
- `token.encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。

### require_admin（第 58 行）

检查已认证身份的写权限；无权限抛出 HTTPException(403)。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码

## app/config.py

### get_settings（第 45 行）

调用 Settings() 解析并缓存配置。

内部使用：

- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。

## app/main.py

### create_app（第 13 行）

token_map 校验认证配置，RAGPipeline 初始化目录，include_router 注册接口。

内部使用：

- `BoundedSemaphore()`：创建有最大数量的进程内执行名额，防止无限并发占用模型资源
- `FastAPI()`：构造 HTTP 应用
- `RAGPipeline()`：构造对象：应用级只读模型对象 + 每请求独立检索快照；不改变共享配置。
- `app.include_router()`：注册 HTTP 路由
- `get_settings()`：调用 Settings() 解析并缓存配置。
- `token_map()`：读取服务端令牌与身份映射，正文不能指定权限

### run（第 24 行）

get_settings 读取地址，uvicorn.run 启动服务；默认只允许本机访问。

内部使用：

- `create_app()`：token_map 校验认证配置，RAGPipeline 初始化目录，include_router 注册接口。
- `get_settings()`：调用 Settings() 解析并缓存配置。
- `uvicorn.run()`：在配置的地址启动 HTTP 服务

## app/rag/catalog.py

### nonblank（第 31 行）

str.strip 检查空白原文；不修改原文，保持行号。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `field_validator()`：声明 Pydantic 自定义字段校验器
- `value.strip()`：去掉首尾空白

### valid_url（第 39 行）

urlparse 限制 HTTP(S) 来源；这里只保存链接，不访问该地址。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `field_validator()`：声明 Pydantic 自定义字段校验器
- `urlparse()`：拆解来源 URL 并限制允许的协议

### __init__（第 50 行）

mkdir 建目录，_connect 和 executescript 建表、外键及权限索引。

内部使用：

- `con.executescript()`：创建表、外键与索引
- `self._connect()`：connect 建独立连接；成功提交、异常回滚，finally 关闭连接。
- `settings.db_path.parent.mkdir()`：创建项目数据目录

### _connect（第 72 行）

connect 建独立连接；成功提交、异常回滚，finally 关闭连接。

内部使用：

- `con.close()`：关闭连接，释放资源
- `con.commit()`：提交完整事务
- `con.execute()`：执行带参数的 SQL 查询或单条更新
- `con.rollback()`：异常时撤销未提交修改
- `sqlite3.connect()`：建立一次数据库连接

### _check_model（第 86 行）

execute 读取模型指纹；拒绝混合不同模型的向量。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `con.execute()`：执行带参数的 SQL 查询或单条更新
- `con.execute("SELECT value FROM meta WHERE key='model'").fetchone()`：读取一个 SQL 查询结果

### upsert（第 92 行）

chunk_text 分块、encode 算向量，BEGIN IMMEDIATE 原子替换；摘要相同则跳过。

内部使用：

- `PermissionError()`：表示可信身份没有写入权限
- `ValueError()`：表示输入或数据不符合约束
- `asdict()`：把数据类及其嵌套字段转换为字典
- `chunk_text()`：get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。
- `con.execute()`：执行带参数的 SQL 查询或单条更新
- `con.execute("SELECT value FROM meta WHERE key='dimension'").fetchone()`：读取一个 SQL 查询结果
- `con.execute('SELECT revision FROM documents WHERE tenant=? AND doc_id=?', (principal.tenant_id, document.doc_id)).fetchone()`：读取一个 SQL 查询结果
- `con.executemany()`：在同一事务内批量写入片段和向量
- `document.model_dump()`：导出已经通过 Pydantic 验证的文档字段
- `embedder.encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(json.dumps({**document.model_dump(), 'model': embedder.fingerprint, 'chunking': ['heading-lines-v1', self.settings.chunk_size, self.settings.chunk_overlap]}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()`：把摘要转换为十六进制标识
- `int()`：转换整数编号、维度或端口
- `json.dumps()`：把对象序列化为 JSON
- `json.dumps({**document.model_dump(), 'model': embedder.fingerprint, 'chunking': ['heading-lines-v1', self.settings.chunk_size, self.settings.chunk_overlap]}, sort_keys=True, ensure_ascii=False).encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `np.any()`：检查是否存在无效向量条目
- `np.asarray()`：把模型输出转换为统一 float32 数组
- `np.isfinite()`：拒绝 NaN 或无穷大的向量
- `np.isfinite(embeddings).all()`：检查所有项目或向量值都满足条件
- `np.linalg.norm()`：计算向量长度，用于 L2 归一化
- `replace()`：复制不可变数据类并更新指定字段
- `self._check_model()`：execute 读取模型指纹；拒绝混合不同模型的向量。
- `self._connect()`：connect 建独立连接；成功提交、异常回滚，finally 关闭连接。
- `str()`：转换路径或错误信息为字符串
- `vector.tobytes()`：将 float32 向量序列化成 SQLite BLOB
- `zip()`：逐项配对数据；strict=True 会拒绝两侧长度不一致

### _scope（第 193 行）

生成参数化权限条件；tenant 始终限制，管理员仅跳过部门过滤。

内部使用：

- `','.join()`：连接字符串片段

### snapshot（第 201 行）

_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。

内部使用：

- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `VectorStore()`：构造对象：单次请求的可见文档快照，不共享可变排名和 top_k。
- `con.execute()`：执行带参数的 SQL 查询或单条更新
- `con.execute(f'SELECT c.payload,c.embedding FROM chunks c JOIN documents d\n                ON d.tenant=c.tenant AND d.doc_id=c.doc_id WHERE {scope}\n                ORDER BY c.doc_id,c.ordinal', params).fetchall()`：读取全部 SQL 查询结果
- `json.loads()`：把 JSON 文本解析为结构化对象
- `np.frombuffer()`：从 SQLite BLOB 还原 float32 向量
- `np.stack()`：把多条向量拼成检索矩阵
- `self._check_model()`：execute 读取模型指纹；拒绝混合不同模型的向量。
- `self._connect()`：connect 建独立连接；成功提交、异常回滚，finally 关闭连接。
- `self._scope()`：生成参数化权限条件；tenant 始终限制，管理员仅跳过部门过滤。
- `store.add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。

### documents（第 221 行）

_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。

内部使用：

- `con.execute()`：执行带参数的 SQL 查询或单条更新
- `dict()`：构造映射或把 SQLite Row 转为字典
- `params.append()`：向列表增加一条记录
- `self._connect()`：connect 建独立连接；成功提交、异常回滚，finally 关闭连接。
- `self._scope()`：生成参数化权限条件；tenant 始终限制，管理员仅跳过部门过滤。

### delete（第 237 行）

检查写权限，execute 删除租户内文档；外键同时清理旧片段。

内部使用：

- `PermissionError()`：表示可信身份没有写入权限
- `con.execute()`：执行带参数的 SQL 查询或单条更新
- `self._connect()`：connect 建独立连接；成功提交、异常回滚，finally 关闭连接。

## app/rag/chunking.py

### __len__（第 25 行）

len(self.text) 返回字符数；不把字符数当作 Token 数。

内部使用：

- `len()`：统计字符数或条目数；这里不是 Token 计数器

### chunk_text（第 30 行）

get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。

内部使用：

- `'\n'.join()`：连接字符串片段
- `'\n'.join((line for _, line in buffer)).strip()`：去掉首尾空白
- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `ValueError()`：表示输入或数据不符合约束
- `bool()`：把标题匹配结果转换为真或假
- `buffer.append()`：向列表增加一条记录
- `chr()`：按字符编码取得代码围栏标记
- `chunks.append()`：向列表增加一条记录
- `enumerate()`：同时获得条目及位置编号
- `f'{source}:{c.index}:{c.text}'.encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `flush()`：Chunk 输出缓冲区；len 控制保留的完整尾行，不跨标题重叠。
- `get_settings()`：调用 Settings() 解析并缓存配置。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(f'{source}:{c.index}:{c.text}'.encode()).hexdigest()`：把摘要转换为十六进制标识
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `line.lstrip()`：清理标题前缀
- `line.lstrip().startswith()`：检查协议、标题或围栏前缀
- `max()`：选择较大值，保护归一化分母或候选数量
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `re.match()`：从行首识别标题
- `re.sub()`：去掉 Markdown 标题中的锚点注记
- `re.sub('\\s*\\{.*?\\}\\s*$', '', line.lstrip('# ')).strip()`：去掉首尾空白
- `replace()`：复制不可变数据类并更新指定字段
- `reversed()`：从尾部读取完整行以构造重叠段
- `tail.insert()`：在指定位置添加完整尾行
- `text.splitlines()`：按原始换行拆分文本

### flush（第 47 行）

Chunk 输出缓冲区；len 控制保留的完整尾行，不跨标题重叠。

内部使用：

- `'\n'.join()`：连接字符串片段
- `'\n'.join((line for _, line in buffer)).strip()`：去掉首尾空白
- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `chunks.append()`：向列表增加一条记录
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `reversed()`：从尾部读取完整行以构造重叠段
- `tail.insert()`：在指定位置添加完整尾行

### chunk_documents（第 84 行）

批量调用 chunk_text，保留各文档 source。

内部使用：

- `chunk_text()`：get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。
- `get_settings()`：调用 Settings() 解析并缓存配置。

## app/rag/cost.py

### usage_report（第 4 行）

仅在 Token 和两项价格均已知时计算金额；不估算本地模型 Token 成本。

内部使用：

- 无额外函数调用。

## app/rag/embeddings.py

### __init__（第 14 行）

保存配置并建立 Lock；构造时不下载模型。

内部使用：

- `Lock()`：保护模型首次初始化，避免并发重复加载

### _load（第 24 行）

锁内首次构造 TextEmbedding，避免多个请求同时加载。

内部使用：

- `TextEmbedding()`：创建本地 FastEmbed 语义向量模型
- `model_path()`：查找固定快照；缺失时 snapshot_download 下载该提交，而非滚动 main。
- `str()`：转换路径或错误信息为字符串

### encode（第 42 行）

passage_embed 算文档向量，np.linalg.norm 做 L2 归一化。

内部使用：

- `list()`：把迭代结果收集为列表
- `np.array()`：构造数值数组
- `np.empty()`：创建空矩阵以表示没有可见片段
- `np.linalg.norm()`：计算向量长度，用于 L2 归一化
- `np.maximum()`：限制除数下界，避免除零
- `self._load()`：锁内首次构造 TextEmbedding，避免多个请求同时加载。
- `self._load().passage_embed()`：用固定版本语义模型计算文档片段向量

### encode_query（第 49 行）

query_embed 算查询向量，再归一化；与文档使用同一模型。

内部使用：

- `float()`：把 NumPy 分数转换为可序列化数值
- `iter()`：取得迭代器，便于读取模型向量
- `max()`：选择较大值，保护归一化分母或候选数量
- `next()`：从迭代器获取首个结果或指定默认值
- `np.array()`：构造数值数组
- `np.linalg.norm()`：计算向量长度，用于 L2 归一化
- `self._load()`：锁内首次构造 TextEmbedding，避免多个请求同时加载。
- `self._load().query_embed()`：用同一语义模型计算查询向量

## app/rag/evidence.py

### technical_identifiers（第 9 行）

提取显式代码标识符、驼峰 API 名及 yield/finally；普通词不触发额外召回。

内部使用：

- `name.lower()`：把文本统一成小写以分词匹配
- `re.findall()`：提取全部关键词

### code_document_id（第 19 行）

将固定 docs_src Python 示例路径转换为本地文档 ID；拒绝目录穿越与任意 URL。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `path.removeprefix()`：去掉固定路径前缀，不执行文件访问
- `path.removeprefix('docs_src/').removesuffix()`：去掉文件后缀
- `path.removeprefix('docs_src/').removesuffix('.py').replace()`：复制不可变数据类并更新指定字段
- `re.fullmatch()`：判断整个字符串是否为中文

### select_context（第 26 行）

先筛可靠锚点，再从同一权限快照添加其代码引用与相邻片段；记录每次选择原因。

内部使用：

- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。
- `_tokenize()`：re.findall 保留技术标识符；中文切为字和二元组；过滤常见英文虚词。
- `abs()`：计算片段编号距离，只扩展紧邻的前后片段
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `code_document_id()`：将固定 docs_src Python 示例路径转换为本地文档 ID；拒绝目录穿越与任意 URL。
- `context.append()`：向列表增加一条记录
- `decisions.append()`：向列表增加一条记录
- `dict.fromkeys()`：按出现顺序去重代码引用路径
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `literal.append()`：向列表增加一条记录
- `literal.sort()`：按明确规则排序本次候选，不修改全局索引
- `pair[1].source.startswith()`：检查协议、标题或围栏前缀
- `re.findall()`：提取全部关键词
- `seen.add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `set()`：去重，例如被实际使用的引用编号
- `sorted()`：按照指定分数排序并保持可重复的顺序
- `technical_identifiers()`：提取显式代码标识符、驼峰 API 名及 yield/finally；普通词不触发额外召回。

### add（第 39 行）

按 chunk_id 去重并限制总数；附加来源不伪造向量分数，记录锚点 ID。

内部使用：

- `context.append()`：向列表增加一条记录
- `decisions.append()`：向列表增加一条记录
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `seen.add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。

### evidence_spans（第 105 行）

按空行及长度切出原文子串，不改写内容；剔除占位指令，单个引用不超过 800 字符。

内部使用：

- `EvidenceSpan()`：构造对象：程序控制的原文单元，编号只在当前请求对应片段内有效。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `paragraph[start:start + 800].strip()`：去掉首尾空白
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `re.fullmatch()`：判断整个字符串是否为中文
- `re.split()`：按分隔符切分字符串
- `spans.append()`：向列表增加一条记录

## app/rag/generation.py

### __init__（第 92 行）

RuntimeError 保存固定错误码，供接口和评测区分超时、限流及连接故障。

内部使用：

- `super()`：取得父类接口，用于初始化标准异常对象
- `super().__init__()`：初始化父类 RuntimeError，保存稳定错误码

### validate_draft（第 98 行）

检查还原引用的范围及原文子串；字串存在不能代替语义支持关系评审。

内部使用：

- `CitationValidationError()`：构造对象：稳定诊断码；不把未校验的草稿或密钥带入用户错误信息。
- `evidence.quote.strip()`：去掉首尾空白
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `re.search()`：搜索匹配的引用标号
- `set()`：去重，例如被实际使用的引用编号
- `sorted()`：按照指定分数排序并保持可重复的顺序
- `used.add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。

### resolve_references（第 116 行）

将有效片段/单元 ID 还原成服务器已有 quote；拒绝不存在的任意编号。

内部使用：

- `CitationValidationError()`：构造对象：稳定诊断码；不把未校验的草稿或密钥带入用户错误信息。
- `Claim()`：构造对象：还原后的陈述和原文证据；Pydantic 拒绝额外字段。
- `Draft()`：构造对象：还原后的完整回答；空列表代表证据不足。
- `Evidence()`：构造对象：服务端还原后的引用；原文必须来自本次证据，保持旧验证接口可读。
- `claims.append()`：向列表增加一条记录
- `evidence.append()`：向列表增加一条记录
- `len()`：统计字符数或条目数；这里不是 Token 计数器

### __init__（第 135 行）

保存只读配置；可选诊断回调只用于授权的离线评测，日常接口不保存原始草稿。

内部使用：

- `ValueError()`：表示输入或数据不符合约束

### _request（第 141 行）

真实 SDK 发结构化请求；timeout/connection/status 分别转换，网络失败不自动重试。

内部使用：

- `GenerationUnavailable()`：构造对象：上游故障分类；网络错误不会触发内容纠正重试。
- `client.chat.completions.create()`：发送带证据的结构化生成请求，读取服务商真实 usage

### generate（第 161 行）

确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。

内部使用：

- `' '.join()`：连接字符串片段
- `'\n'.join()`：连接字符串片段
- `'\n\n'.join()`：连接字符串片段
- `CitationValidationError()`：构造对象：稳定诊断码；不把未校验的草稿或密钥带入用户错误信息。
- `GenerationResult()`：构造对象：请求内结果；包含累计实际消耗、校验轨迹及真正使用的引用。
- `GenerationUnavailable()`：构造对象：上游故障分类；网络错误不会触发内容纠正重试。
- `OpenAI()`：创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型
- `SelectedDraft.model_validate_json()`：校验模型只能提交语言、陈述和合法格式的编号引用
- `ValueError()`：表示输入或数据不符合约束
- `answer_language()`：检查显式 en/zh/auto；自动模式对含中文的本项目问题选择中文，否则英文。
- `asdict()`：把数据类及其嵌套字段转换为字典
- `attempts.append()`：向列表增加一条记录
- `c.model_dump()`：导出已经通过 Pydantic 验证的文档字段
- `check_language()`：移除代码和 URL 后识别正文；短技术表达记为不确定，高置信度外语判不匹配。
- `enumerate()`：同时获得条目及位置编号
- `evidence_spans()`：按空行及长度切出原文子串，不改写内容；剔除占位指令，单个引用不超过 800 字符。
- `exc.errors()`：取得校验位置和错误类型；报告不保存异常中的密钥或配置对象
- `hasattr()`：检查异常是否提供结构化校验细节
- `isinstance()`：检查配置对象类型
- `json.dumps()`：把对象序列化为 JSON
- `language_result.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `messages.extend()`：批量增加记录
- `min()`：限制返回数量
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `record.update()`：批量更新当前请求记录或独立配置副本中的字段
- `resolve_references()`：将有效片段/单元 ID 还原成服务器已有 quote；拒绝不存在的任意编号。
- `self._request()`：真实 SDK 发结构化请求；timeout/connection/status 分别转换，网络失败不自动重试。
- `self.diagnostic_sink()`：仅评测时记录拒绝草稿和细分原因；日常接口没有这个回调
- `self.settings.llm_api_key.get_secret_value()`：只在必要调用时取得配置值，不输出密钥
- `sorted()`：按照指定分数排序并保持可重复的顺序
- `str()`：转换路径或错误信息为字符串
- `validate_draft()`：检查还原引用的范围及原文子串；字串存在不能代替语义支持关系评审。
- `zip()`：逐项配对数据；strict=True 会拒绝两侧长度不一致

## app/rag/language.py

### answer_language（第 10 行）

检查显式 en/zh/auto；自动模式对含中文的本项目问题选择中文，否则英文。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `re.findall()`：提取全部关键词

### language_factory（第 20 行）

加载安装包自带的语言特征并固定 seed；每次检查创建独立检测器，避免共享请求状态。

内部使用：

- `DetectorFactory()`：构造本地语言识别器工厂，资料随安装包提供
- `factory.load_profile()`：读取本地字符统计特征，不调用外部模型
- `factory.set_seed()`：固定语言识别随机种子，便于复现判断

### check_language（第 28 行）

移除代码和 URL 后识别正文；短技术表达记为不确定，高置信度外语判不匹配。

内部使用：

- `detector.append()`：向列表增加一条记录
- `detector.get_probabilities()`：取得正文语言及置信度，不使用引用原文作为回答语言
- `first.lang.startswith()`：检查协议、标题或围栏前缀
- `language_factory()`：加载安装包自带的语言特征并固定 seed；每次检查创建独立检测器，避免共享请求状态。
- `language_factory().create()`：为当前检查建立独立识别器，隔离请求状态
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `re.findall()`：提取全部关键词
- `re.sub()`：去掉 Markdown 标题中的锚点注记

## app/rag/model_files.py

### model_path（第 6 行）

查找固定快照；缺失时 snapshot_download 下载该提交，而非滚动 main。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `all()`：检查所有项目或向量值都满足条件
- `p.is_file()`：检查固定模型缓存是否完整
- `repo.replace()`：复制不可变数据类并更新指定字段
- `repo.startswith()`：检查协议、标题或围栏前缀
- `snapshot_download()`：下载固定提交的公开模型文件，已有缓存时不联网
- `str()`：转换路径或错误信息为字符串

## app/rag/pipeline.py

### __init__（第 22 行）

构造 Catalog 与可延迟加载的组件；允许测试注入组件，避免下载模型。

内部使用：

- `Catalog()`：构造对象：文档目录；SQLite 并非向量数据库，当前小规模向量检索在内存执行。
- `Embedder()`：构造对象：保留上游 Embedder 接口，首次使用时加载模型。
- `Generator()`：构造对象：默认摘录；compatible 使用编号引用、语言检查与最多一次内容纠正。
- `Reranker()`：构造对象：复用上游重排职责，以 FastEmbed/ONNX 替代 Torch。
- `get_settings()`：调用 Settings() 解析并缓存配置。

### retrieve（第 32 行）

snapshot 先过滤权限；HybridRetriever 召回，按模式 Reranker 重排，记录分阶段耗时。

内部使用：

- `HybridRetriever()`：构造对象：仅处理 Catalog 已过滤权限的快照，不能接触不可见文档。
- `ValueError()`：表示输入或数据不符合约束
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `max()`：选择较大值，保护归一化分母或候选数量
- `perf_counter()`：测量检索、重排、生成阶段的实际耗时
- `question.strip()`：去掉首尾空白
- `retriever.retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。
- `self.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `self.reranker.rerank()`：切片保留调用方要求数量；真实重排模型通过独立 benchmark 验证。

### query（第 69 行）

retrieve 召回，select_context 补齐授权证据，generate 校验引用与语言，统计耗时和消耗。

内部使用：

- `asdict()`：把数据类及其嵌套字段转换为字典
- `perf_counter()`：测量检索、重排、生成阶段的实际耗时
- `select_context()`：先筛可靠锚点，再从同一权限快照添加其代码引用与相邻片段；记录每次选择原因。
- `self.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `self.generator.generate()`：确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。
- `self.retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。
- `usage_report()`：仅在 Token 和两项价格均已知时计算金额；不估算本地模型 Token 成本。

## app/rag/reranking.py

### __init__（第 14 行）

保存模型配置，Lock 保护首次加载；不在初始化时联网。

内部使用：

- `Lock()`：保护模型首次初始化，避免并发重复加载

### _load（第 19 行）

锁内构造 TextCrossEncoder；已加载时直接复用只读模型。

内部使用：

- `TextCrossEncoder()`：创建本地查询与片段联合打分的重排模型
- `model_path()`：查找固定快照；缺失时 snapshot_download 下载该提交，而非滚动 main。
- `str()`：转换路径或错误信息为字符串

### rerank（第 37 行）

模型 rerank 计算相关性；replace 增加重排分数；sorted 截取最高结果。

内部使用：

- `float()`：把 NumPy 分数转换为可序列化数值
- `list()`：把迭代结果收集为列表
- `replace()`：复制不可变数据类并更新指定字段
- `self._load()`：锁内构造 TextCrossEncoder；已加载时直接复用只读模型。
- `self._load().rerank()`：切片保留调用方要求数量；真实重排模型通过独立 benchmark 验证。
- `sorted()`：按照指定分数排序并保持可重复的顺序
- `zip()`：逐项配对数据；strict=True 会拒绝两侧长度不一致

## app/rag/retrieval.py

### _tokenize（第 28 行）

re.findall 保留技术标识符；中文切为字和二元组；过滤常见英文虚词。

内部使用：

- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `re.findall()`：提取全部关键词
- `re.fullmatch()`：判断整个字符串是否为中文
- `result.append()`：向列表增加一条记录
- `result.extend()`：批量增加记录
- `text.lower()`：把文本统一成小写以分词匹配

### __init__（第 44 行）

_tokenize 建词表，BM25Okapi 建当前快照的关键词索引。

内部使用：

- `BM25Okapi()`：构建关键词检索索引；项目修正了 IDF 的小语料边界
- `Counter()`：统计每个词出现在多少片段中
- `_tokenize()`：re.findall 保留技术标识符；中文切为字和二元组；过滤常见英文虚词。
- `frequencies.items()`：遍历映射键值
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `math.log1p()`：计算平滑正 IDF，使单篇可见文档也能被关键词命中
- `set()`：去重，例如被实际使用的引用编号

### retrieve（第 57 行）

dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。

内部使用：

- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。
- `ValueError()`：表示输入或数据不符合约束
- `_tokenize()`：re.findall 保留技术标识符；中文切为字和二元组；过滤常见英文虚词。
- `dense_scores.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `dict()`：构造映射或把 SQLite Row 转为字典
- `enumerate()`：同时获得条目及位置编号
- `float()`：把 NumPy 分数转换为可序列化数值
- `int()`：转换整数编号、维度或端口
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `np.argsort()`：按分数排序；stable 使同分结果固定
- `scores.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `self._bm25.get_scores()`：BM25 按查询词计算当前可见语料的相关分数
- `self.embedder.encode_query()`：按 alpha/beta/gamma 生成固定向量并归一化，便于精确断言权限过滤结果。
- `self.store.dense_search()`：矩阵乘法算余弦；稳定 argsort 在同分时保持快照顺序。
- `sorted()`：按照指定分数排序并保持可重复的顺序

## app/rag/store.py

### add（第 26 行）

校验数量和有效值；IndexedChunk 保存条目，清除矩阵缓存。

内部使用：

- `IndexedChunk()`：构造对象：片段、向量与当前快照编号；初始化由 dataclass 生成。
- `ValueError()`：表示输入或数据不符合约束
- `enumerate()`：同时获得条目及位置编号
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `np.isfinite()`：拒绝 NaN 或无穷大的向量
- `np.isfinite(embeddings).all()`：检查所有项目或向量值都满足条件
- `self.chunks.extend()`：批量增加记录
- `zip()`：逐项配对数据；strict=True 会拒绝两侧长度不一致

### matrix（第 38 行）

np.stack 拼接矩阵；缓存仅用于当前请求快照。

内部使用：

- `np.empty()`：创建空矩阵以表示没有可见片段
- `np.stack()`：把多条向量拼成检索矩阵

### dense_search（第 48 行）

矩阵乘法算余弦；稳定 argsort 在同分时保持快照顺序。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `float()`：把 NumPy 分数转换为可序列化数值
- `int()`：转换整数编号、维度或端口
- `np.argsort()`：按分数排序；stable 使同分结果固定

### __len__（第 58 行）

len 返回当前快照片段数。

内部使用：

- `len()`：统计字符数或条目数；这里不是 Token 计数器

## eval/common.py

### evaluation_settings（第 13 行）

Settings 读取 RAG 配置；显式开启时 dotenv_values 临时读取工单密钥，不写入文件。

内部使用：

- `(values.get('MODEL') or '').partition()`：按分隔符拆成前缀、分隔符和后缀，用于 provider/model 配置
- `SecretStr()`：包装测试用密钥，使配置显示时脱敏
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `ValueError()`：表示输入或数据不符合约束
- `dotenv_values()`：读取指定配置文件为映射，不更改进程环境，也不输出密钥
- `settings.model_copy()`：复制配置对象并替换指定字段，避免修改共享配置
- `values.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### copy_catalog（第 41 行）

sqlite3.backup 创建包括 WAL 已提交数据的一致副本；评测不修改用户知识库。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `source.is_file()`：检查固定模型缓存是否完整
- `sqlite3.connect()`：建立一次数据库连接
- `src.backup()`：SQLite 在线一致性备份，包含已提交的 WAL 数据

### latency_summary（第 50 行）

np.percentile 汇总实际墙钟时间；明确失败率与样本数，不把小样本称为 SLA。

内部使用：

- `float()`：把 NumPy 分数转换为可序列化数值
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `max()`：选择较大值，保护归一化分母或候选数量
- `np.percentile()`：按实测样本计算 P50/P95；小样本百分位不代表线上 SLA
- `sum()`：累计命中数或费用

## eval/human_review.py

### review_summary（第 39 行）

按实际填写数量和完整任务标准计算比例；未审完时全量成功率为空，不把作者算第三方。

内部使用：

- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `r.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `sum()`：累计命中数或费用

### load_source_documents（第 65 行）

读取并核对固定语料摘要，加上明确标记的虚构评测资料，供人工展开完整原文。

内部使用：

- `(PROJECT_ROOT / 'data/corpus' / name).read_text()`：读取 UTF-8 文本
- `(PROJECT_ROOT / item['file']).read_bytes()`：读取原始字节用于摘要核验
- `ValueError()`：表示输入或数据不符合约束
- `dataset.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `json.loads()`：把 JSON 文本解析为结构化对象
- `raw.decode()`：把原文字节解码为 UTF-8 文本

### __init__（第 93 行）

核对完整报告、唯一 ID 与旧评分来源；恢复人工记录，首次建立全部待审核文件。

内部使用：

- `HumanScore.model_validate()`：校验恢复的评分需要明确布尔判断，拒绝用字符串或数字冒充人工通过
- `Lock()`：保护模型首次初始化，避免并发重复加载
- `ValueError()`：表示输入或数据不符合约束
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `existing['scores'].items()`：遍历映射键值
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `output.is_file()`：检查固定模型缓存是否完整
- `output.read_text()`：读取 UTF-8 文本
- `output.resolve()`：取得规范绝对路径，用于防止评分文件覆盖原报告
- `self._persist()`：临时文件完成写入后 os.replace 原子替换评分；异常时清理临时文件。
- `self._record()`：校验适用性和失败备注；五项人工判断与程序状态边界共同决定完整任务成功。
- `source.read_bytes()`：读取原始字节用于摘要核验
- `source.resolve()`：取得规范绝对路径，用于防止评分文件覆盖原报告

### _check_source（第 127 行）

每次读取或保存前确认冻结报告未被修改，防止把评分绑定到另一批回答。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(self.source.read_bytes()).hexdigest()`：把摘要转换为十六进制标识
- `self.source.read_bytes()`：读取原始字节用于摘要核验

### _record（第 132 行）

校验适用性和失败备注；五项人工判断与程序状态边界共同决定完整任务成功。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `all()`：检查所有项目或向量值都满足条件
- `data['notes'].strip()`：去掉首尾空白
- `data['reviewer_name'].strip()`：去掉首尾空白
- `row.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `row.get('mechanical_review', {}).get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `score.model_dump()`：导出已经通过 Pydantic 验证的文档字段

### _bundle（第 155 行）

生成带来源摘要、身份类别、逐题记录和正确分母的人工评分汇总。

内部使用：

- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `list()`：把迭代结果收集为列表
- `review_summary()`：按实际填写数量和完整任务标准计算比例；未审完时全量成功率为空，不把作者算第三方。
- `self.rows.values()`：遍历映射值

### _persist（第 170 行）

临时文件完成写入后 os.replace 原子替换评分；异常时清理临时文件。

内部使用：

- `NamedTemporaryFile()`：创建仅本次写入使用的临时文件，写完后原子替换评分文件
- `Path()`：构造文件路径对象，用于定位项目内源码、数据和报告
- `file.write()`：写入评分文件的结尾换行，不调用外部服务
- `json.dump()`：把真实人工记录序列化写入临时文件，不生成任何评分
- `os.replace()`：原子替换本地评分文件，避免只写一半的评分被读取
- `self._bundle()`：生成带来源摘要、身份类别、逐题记录和正确分母的人工评分汇总。
- `self.output.parent.mkdir()`：创建项目数据目录
- `temporary.unlink()`：清理本次临时文件或临时测试文件，不删除原评测报告

### export（第 191 行）

加锁读取真实人工评分；检查来源，返回副本，避免调用者修改共享状态。

内部使用：

- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `self._bundle()`：生成带来源摘要、身份类别、逐题记录和正确分母的人工评分汇总。
- `self._check_source()`：每次读取或保存前确认冻结报告未被修改，防止把评分绑定到另一批回答。

### save（第 197 行）

按唯一题号保存一次明确人工输入；写盘失败恢复旧记录，原报告始终不变。

内部使用：

- `KeyError()`：拒绝不存在的评测题号，不能保存额外或伪造记录
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `self._bundle()`：生成带来源摘要、身份类别、逐题记录和正确分母的人工评分汇总。
- `self._check_source()`：每次读取或保存前确认冻结报告未被修改，防止把评分绑定到另一批回答。
- `self._persist()`：临时文件完成写入后 os.replace 原子替换评分；异常时清理临时文件。
- `self._record()`：校验适用性和失败备注；五项人工判断与程序状态边界共同决定完整任务成功。
- `self.scores.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `self.scores.pop()`：写盘失败时撤回未保存的内存评分，恢复原有状态

### material（第 216 行）

仅展示原问题、回答、证据和人工记录，省略 AI 评分、通过提示与无效模型草稿。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `json.loads()`：把 JSON 文本解析为结构化对象
- `records.items()`：遍历映射键值
- `self.export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `self.rows.values()`：遍历映射值
- `self.source.with_name()`：构造同目录的辅助译文路径，不重命名或覆盖原始评测文件
- `translation_path.is_file()`：检查固定模型缓存是否完整
- `translation_path.read_text()`：读取 UTF-8 文本

### create_review_app（第 252 行）

只为本机人工审核注册页面、读取、下载和保存接口，不调用检索或生成模型。

内部使用：

- `(PROJECT_ROOT / 'eval/review_ui.html').read_text()`：读取 UTF-8 文本
- `FastAPI()`：构造 HTTP 应用
- `HTMLResponse()`：返回静态问答界面
- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `JSONResponse()`：返回真实人工记录的 JSON，不把待审核项补成通过
- `app.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `app.post()`：发送测试 POST 请求
- `request.headers.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `store.export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `store.material()`：读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `str()`：转换路径或错误信息为字符串

### home（第 257 行）

返回人工评分页面；禁用跨域嵌入，页面不包含任何模型密钥。

内部使用：

- `(PROJECT_ROOT / 'eval/review_ui.html').read_text()`：读取 UTF-8 文本
- `HTMLResponse()`：返回静态问答界面
- `app.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### material（第 265 行）

读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `app.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `store.material()`：读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。
- `str()`：转换路径或错误信息为字符串

### export（第 273 行）

下载已经保存的真实人工评分，待审项不补写为成功。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `JSONResponse()`：返回真实人工记录的 JSON，不把待审核项补成通过
- `app.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `store.export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `str()`：转换路径或错误信息为字符串

### save（第 284 行）

要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。

内部使用：

- `HTTPException()`：让 HTTP 层返回指定错误状态码
- `app.post()`：发送测试 POST 请求
- `request.headers.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `str()`：转换路径或错误信息为字符串

## eval/metrics.py

### normalize（第 4 行）

split/join 统一空白，使跨行但内容一致的摘录可以匹配。

内部使用：

- `' '.join()`：连接字符串片段
- `text.split()`：按分隔符切分字符串

### evidence_metrics（第 9 行）

按文档 ID + 原文摘录判定命中，计算证据覆盖率、Any/All-Gold@K 和 MRR。

内部使用：

- `all()`：检查所有项目或向量值都满足条件
- `any()`：检查是否存在匹配值或非零向量分量
- `enumerate()`：同时获得条目及位置编号
- `float()`：把 NumPy 分数转换为可序列化数值
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `next()`：从迭代器获取首个结果或指定默认值
- `normalize()`：split/join 统一空白，使跨行但内容一致的摘录可以匹配。
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `sum()`：累计命中数或费用

### recall_at_k（第 28 行）

保留上游文档级兼容指标；新评测使用 evidence_metrics 避免仅找到文档就算成功。

内部使用：

- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `set()`：去重，例如被实际使用的引用编号
- `sum()`：累计命中数或费用

### mrr（第 37 行）

保留上游 MRR 辅助函数；enumerate 寻找首个相关来源的倒数排名。

内部使用：

- `enumerate()`：同时获得条目及位置编号
- `next()`：从迭代器获取首个结果或指定默认值

## eval/run_answers.py

### mechanical_review（第 29 行）

检查状态、候选及实际模型上下文的权限与合成标记；字串检查不能代替语义评审。

内部使用：

- `bool()`：把标题匹配结果转换为真或假
- `case.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `result.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `set()`：去重，例如被实际使用的引用编号
- `sorted()`：按照指定分数排序并保持可重复的顺序

### answer_summary（第 57 行）

汇总 API 实际 usage、错误及边界结果；未填人工或助手评分不算通过。

内部使用：

- `bool()`：把标题匹配结果转换为真或假
- `groups.setdefault()`：如果映射中没有当前分类，就创建其累计统计项
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `r.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `r.get('assistant_review', {}).get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `r.get('human_review', {}).get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `row.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `row.get('mechanical_review', {}).get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `sum()`：累计命中数或费用
- `u.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### main（第 80 行）

副本中 query 执行真实生成；逐题保存可续跑报告，记录证据并留下待评审字段。

内部使用：

- `''.join()`：连接字符串片段
- `''.join((c.chunk.revision + c.chunk.chunk_id for c in snapshot.chunks)).encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `(PROJECT_ROOT / args.dataset).read_bytes()`：读取原始字节用于摘要核验
- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `DocumentInput()`：构造对象：Pydantic 拒绝额外身份字段，校验 ID、原文长度和来源链接。
- `Path()`：构造文件路径对象，用于定位项目内源码、数据和报告
- `RAGPipeline()`：构造对象：应用级只读模型对象 + 每请求独立检索快照；不改变共享配置。
- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。
- `TemporaryDirectory()`：创建隔离临时目录，退出上下文时清理其文件
- `answer_summary()`：汇总 API 实际 usage、错误及边界结果；未填人工或助手评分不算通过。
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `base.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `base.update()`：批量更新当前请求记录或独立配置副本中的字段
- `case.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `copy_catalog()`：sqlite3.backup 创建包括 WAL 已提交数据的一致副本；评测不修改用户知识库。
- `dataset.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `evaluation_settings()`：Settings 读取 RAG 配置；显式开启时 dotenv_values 临时读取工单密钥，不写入文件。
- `evidence_metrics()`：按文档 ID + 原文摘录判定命中，计算证据覆盖率、Any/All-Gold@K 和 MRR。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(''.join((c.chunk.revision + c.chunk.chunk_id for c in snapshot.chunks)).encode()).hexdigest()`：把摘要转换为十六进制标识
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `isinstance()`：检查配置对象类型
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `mechanical_review()`：检查状态、候选及实际模型上下文的权限与合成标记；字串检查不能代替语义评审。
- `parser.add_argument()`：声明命令行输入与范围
- `parser.error()`：拒绝错误的评测运行参数
- `parser.parse_args()`：解析命令行参数
- `path.is_file()`：检查固定模型缓存是否完整
- `path.parent.mkdir()`：创建项目数据目录
- `path.read_text()`：读取 UTF-8 文本
- `path.write_text()`：写入文档或评测报告
- `perf_counter()`：测量检索、重排、生成阶段的实际耗时
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `pipeline.catalog.upsert()`：chunk_text 分块、encode 算向量，BEGIN IMMEDIATE 原子替换；摘要相同则跳过。
- `pipeline.query()`：仅用于占满测试名额；Event 通知主线程，不让等待超过两秒。
- `print()`：输出本次脚本运行进度，不输出密钥
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `rows.append()`：向列表增加一条记录
- `set()`：去重，例如被实际使用的引用编号
- `settings.llm_api_key.get_secret_value()`：只在必要调用时取得配置值，不输出密钥
- `settings.model_copy()`：复制配置对象并替换指定字段，避免修改共享配置
- `type()`：取得异常类型以记录失败，不输出可能敏感的异常内容

## eval/run_eval.py

### validate_set（第 17 行）

检查 ID 唯一及每条 gold 对应真实原文片段；避免坏标签被计为模型失败。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `any()`：检查是否存在匹配值或非零向量分量
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `normalize()`：split/join 统一空白，使跨行但内容一致的摘录可以匹配。
- `set()`：去重，例如被实际使用的引用编号

### main（第 34 行）

读取标注集，validate_set 校验；retrieve 执行四路对照，保存完整结果与汇总。

内部使用：

- `''.join()`：连接字符串片段
- `''.join((c.chunk.revision + c.chunk.chunk_id for c in store.chunks)).encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `(PROJECT_ROOT / args.dataset).read_bytes()`：读取原始字节用于摘要核验
- `RAGPipeline()`：构造对象：应用级只读模型对象 + 每请求独立检索快照；不改变共享配置。
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `evidence_metrics()`：按文档 ID + 原文摘录判定命中，计算证据覆盖率、Any/All-Gold@K 和 MRR。
- `group.append()`：向列表增加一条记录
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(''.join((c.chunk.revision + c.chunk.chunk_id for c in store.chunks)).encode()).hexdigest()`：把摘要转换为十六进制标识
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `mean()`：对重复实验计算均值；重复运行不是新增独立样本
- `output.parent.mkdir()`：创建项目数据目录
- `output.write_text()`：写入文档或评测报告
- `parser.add_argument()`：声明命令行输入与范围
- `parser.parse_args()`：解析命令行参数
- `perf_counter()`：测量检索、重排、生成阶段的实际耗时
- `pipeline.catalog.documents()`：_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `pipeline.retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。
- `platform.platform()`：记录测试机器环境
- `print()`：输出本次脚本运行进度，不输出密钥
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `rows.append()`：向列表增加一条记录
- `validate_set()`：检查 ID 唯一及每条 gold 对应真实原文片段；避免坏标签被计为模型失败。

## eval/run_live_stability.py

### main（第 24 行）

临时服务只在进程环境中取得授权密钥，ask_once 记录真实生成并发与实际消耗。

内部使用：

- `Path()`：构造文件路径对象，用于定位项目内源码、数据和报告
- `SystemExit()`：让验证脚本用非零退出码报告真实失败
- `TemporaryDirectory()`：创建隔离临时目录，退出上下文时清理其文件
- `ThreadPoolExecutor()`：并行下载或执行并发边界测试
- `all()`：检查所有项目或向量值都满足条件
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `ask_once()`：httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。
- `copy_catalog()`：sqlite3.backup 创建包括 WAL 已提交数据的一致副本；评测不修改用户知识库。
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `evaluation_settings()`：Settings 读取 RAG 配置；显式开启时 dotenv_values 临时读取工单密钥，不写入文件。
- `groups.values()`：遍历映射值
- `json.dumps()`：把对象序列化为 JSON
- `latency_summary()`：np.percentile 汇总实际墙钟时间；明确失败率与样本数，不把小样本称为 SLA。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `output.parent.mkdir()`：创建项目数据目录
- `output.write_text()`：写入文档或评测报告
- `parser.add_argument()`：声明命令行输入与范围
- `parser.error()`：拒绝错误的评测运行参数
- `parser.parse_args()`：解析命令行参数
- `platform.platform()`：记录测试机器环境
- `pool.map()`：给线程池分配独立任务
- `print()`：输出本次脚本运行进度，不输出密钥
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `running_service()`：Popen 启动独立服务并轮询 health；finally 只终止自己的进程，避免影响演示服务。
- `settings.llm_api_key.get_secret_value()`：只在必要调用时取得配置值，不输出密钥
- `str()`：转换路径或错误信息为字符串

### run（第 51 行）

ask_once 向真实服务提交固定样本，top_k 保持五，记录实际 HTTP 延迟。

内部使用：

- `ask_once()`：httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。
- `len()`：统计字符数或条目数；这里不是 Token 计数器

## eval/run_stability.py

### ask_once（第 26 行）

httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。

内部使用：

- `all()`：检查所有项目或向量值都满足条件
- `client.post()`：发送测试 POST 请求
- `detail.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `httpx.Client()`：构造 HTTP 客户端
- `isinstance()`：检查配置对象类型
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `payload.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `perf_counter()`：测量检索、重排、生成阶段的实际耗时
- `r['chunk']['source'].startswith()`：检查协议、标题或围栏前缀
- `response.json()`：解析接口返回的 JSON
- `type()`：取得异常类型以记录失败，不输出可能敏感的异常内容

### fault_experiment（第 67 行）

故障上游配合真实服务和 SDK，验证超时/429/500 分类、零自动重试与下一请求恢复。

内部使用：

- `all()`：检查所有项目或向量值都满足条件
- `ask_once()`：httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。
- `fault_provider()`：ThreadingHTTPServer 提供真实本机 HTTP 超时/限流/恢复响应；不冒充真实大模型质量。
- `row.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `rows.append()`：向列表增加一条记录
- `running_service()`：Popen 启动独立服务并轮询 health；finally 只终止自己的进程，避免影响演示服务。

### main（第 98 行）

副本上启动隔离服务，先测冷请求，再测热并发与故障恢复，保存可追溯运行记录。

内部使用：

- `Path()`：构造文件路径对象，用于定位项目内源码、数据和报告
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `SystemExit()`：让验证脚本用非零退出码报告真实失败
- `TemporaryDirectory()`：创建隔离临时目录，退出上下文时清理其文件
- `ThreadPoolExecutor()`：并行下载或执行并发边界测试
- `all()`：检查所有项目或向量值都满足条件
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `ask_once()`：httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。
- `copy_catalog()`：sqlite3.backup 创建包括 WAL 已提交数据的一致副本；评测不修改用户知识库。
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `fault_experiment()`：故障上游配合真实服务和 SDK，验证超时/429/500 分类、零自动重试与下一请求恢复。
- `groups.values()`：遍历映射值
- `json.dumps()`：把对象序列化为 JSON
- `latency_summary()`：np.percentile 汇总实际墙钟时间；明确失败率与样本数，不把小样本称为 SLA。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `parser.add_argument()`：声明命令行输入与范围
- `parser.error()`：拒绝错误的评测运行参数
- `parser.parse_args()`：解析命令行参数
- `path.parent.mkdir()`：创建项目数据目录
- `path.write_text()`：写入文档或评测报告
- `perf_counter()`：测量检索、重排、生成阶段的实际耗时
- `platform.platform()`：记录测试机器环境
- `pool.map()`：给线程池分配独立任务
- `print()`：输出本次脚本运行进度，不输出密钥
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `running_service()`：Popen 启动独立服务并轮询 health；finally 只终止自己的进程，避免影响演示服务。
- `str()`：转换路径或错误信息为字符串

### run（第 117 行）

ask_once 为每项请求传自己的问题和 top_k，线程池限制当前并发档位。

内部使用：

- `ask_once()`：httpx 发真实 HTTP 请求，记录墙钟延迟、状态、参数隔离和来源；不评估语义正确率。
- `len()`：统计字符数或条目数；这里不是 Token 计数器

## eval/runtime.py

### free_port（第 18 行）

socket.bind 让系统选择临时端口；关闭探测 socket 后交给隔离测试服务使用。

内部使用：

- `sock.bind()`：绑定 127.0.0.1 的临时端口，取得可用测试地址
- `sock.getsockname()`：读取操作系统为测试分配的端口
- `socket.socket()`：创建本机端口探测 socket，使用后及时关闭

### running_service（第 26 行）

Popen 启动独立服务并轮询 health；finally 只终止自己的进程，避免影响演示服务。

内部使用：

- `RuntimeError()`：模拟或表示运行阶段的组件故障
- `client.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `dict()`：构造映射或把 SQLite Row 转为字典
- `env.update()`：批量更新当前请求记录或独立配置副本中的字段
- `free_port()`：socket.bind 让系统选择临时端口；关闭探测 socket 后交给隔离测试服务使用。
- `httpx.Client()`：构造 HTTP 客户端
- `process.kill()`：仅强制停止当前脚本创建且无法正常退出的子进程
- `process.poll()`：检查隔离服务是否已经退出，发现启动失败
- `process.terminate()`：请求当前脚本创建的子进程正常停止
- `process.wait()`：等待自己创建的进程退出，设置超时避免无限阻塞
- `str()`：转换路径或错误信息为字符串
- `subprocess.Popen()`：启动隔离 HTTP 服务；密钥只通过进程环境传入
- `time.monotonic()`：读取不受系统时钟校准影响的时间，用于启动截止时间
- `time.sleep()`：短暂等待健康轮询或在测试上游中模拟响应超时

### fault_provider（第 77 行）

ThreadingHTTPServer 提供真实本机 HTTP 超时/限流/恢复响应；不冒充真实大模型质量。

内部使用：

- `Lock()`：保护模型首次初始化，避免并发重复加载
- `Thread()`：构造测试服务或并发请求的后台线程
- `ThreadingHTTPServer()`：创建仅本机可访问的可控 HTTP 上游，模拟错误和恢复
- `int()`：转换整数编号、维度或端口
- `json.dumps()`：把对象序列化为 JSON
- `json.dumps(reply).encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `min()`：限制返回数量
- `self.end_headers()`：完成测试 HTTP 响应头
- `self.rfile.read()`：读取真实 SDK 发来的测试 HTTP 请求体
- `self.send_header()`：写入测试响应的内容类型和长度
- `self.send_response()`：设置测试上游的 HTTP 状态码
- `self.wfile.write()`：发送测试响应体；已超时的连接断开属于预期情况
- `server.server_close()`：关闭故障实验的本机监听 socket
- `server.shutdown()`：停止本机测试上游的请求循环
- `str()`：转换路径或错误信息为字符串
- `thread.join()`：连接字符串片段
- `thread.start()`：启动当前实验的后台线程
- `time.sleep()`：短暂等待健康轮询或在测试上游中模拟响应超时

### log_message（第 85 行）

关闭默认访问日志，避免把测试 HTTP 内容写进报告。

内部使用：

- 无额外函数调用。

### do_POST（第 88 行）

读取 SDK 实际 JSON，按预设动作延迟、返回错误或合法证据，不自动重试。

内部使用：

- `int()`：转换整数编号、维度或端口
- `json.dumps()`：把对象序列化为 JSON
- `json.dumps(reply).encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `min()`：限制返回数量
- `self.end_headers()`：完成测试 HTTP 响应头
- `self.rfile.read()`：读取真实 SDK 发来的测试 HTTP 请求体
- `self.send_header()`：写入测试响应的内容类型和长度
- `self.send_response()`：设置测试上游的 HTTP 状态码
- `self.wfile.write()`：发送测试响应体；已超时的连接断开属于预期情况
- `str()`：转换路径或错误信息为字符串
- `time.sleep()`：短暂等待健康轮询或在测试上游中模拟响应超时

## scripts/explain_functions.py

### functions（第 173 行）

ast.parse 解析模块；walk 查找函数、docstring 和其中全部调用（包含内部小函数）。

内部使用：

- `ast.get_docstring()`：读取源码里的职责解释
- `ast.parse()`：解析 Python 源码，不执行被分析代码
- `ast.unparse()`：把调用目标还原成可读名称
- `ast.walk()`：遍历语法树，发现函数、类和调用表达式
- `isinstance()`：检查配置对象类型
- `output.append()`：向列表增加一条记录
- `path.read_text()`：读取 UTF-8 文本
- `sorted()`：按照指定分数排序并保持可重复的顺序

### main（第 191 行）

functions 生成每个函数的职责及调用清单；使用源码解释与 GLOSSARY 解释被调用函数。

内部使用：

- `'\n'.join()`：连接字符串片段
- `(PROJECT_ROOT / folder).rglob()`：列出源代码文件
- `GLOSSARY.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `ast.get_docstring()`：读取源码里的职责解释
- `ast.parse()`：解析 Python 源码，不执行被分析代码
- `ast.walk()`：遍历语法树，发现函数、类和调用表达式
- `call.split()`：按分隔符切分字符串
- `definitions.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `functions()`：ast.parse 解析模块；walk 查找函数、docstring 和其中全部调用（包含内部小函数）。
- `isinstance()`：检查配置对象类型
- `lines.append()`：向列表增加一条记录
- `lines.extend()`：批量增加记录
- `modules.items()`：遍历映射键值
- `modules.values()`：遍历映射值
- `next()`：从迭代器获取首个结果或指定默认值
- `output.parent.mkdir()`：创建项目数据目录
- `output.write_text()`：写入文档或评测报告
- `path.read_text()`：读取 UTF-8 文本
- `path.relative_to()`：取得项目内的相对路径
- `print()`：输出本次脚本运行进度，不输出密钥
- `sorted()`：按照指定分数排序并保持可重复的顺序
- `{'strip': '去掉首尾空白', 'split': '按分隔符切分字符串', 'splitlines': '按原始换行拆分文本', 'join': '连接字符串片段', 'encode': '编码字符串或计算模型向量，按所属对象区分', 'decode': '把原文字节解码为 UTF-8 文本', 'fetchone': '读取一个 SQL 查询结果', 'fetchall': '读取全部 SQL 查询结果', 'mkdir': '创建项目数据目录', 'read_text': '读取 UTF-8 文本', 'read_bytes': '读取原始字节用于摘要核验', 'write_text': '写入文档或评测报告', 'write_bytes': '保存未经改写的原文或许可证', 'hexdigest': '把摘要转换为十六进制标识', 'model_dump': '导出已经通过 Pydantic 验证的文档字段', 'get_secret_value': '只在必要调用时取得配置值，不输出密钥', 'append': '向列表增加一条记录', 'extend': '批量增加记录', 'insert': '在指定位置添加完整尾行', 'add': '添加去重条目或快照向量', 'get': '安全读取映射键或发送测试 GET 请求，依所属对象区分', 'post': '发送测试 POST 请求', 'delete': '删除文档或发测试 DELETE 请求', 'json': '解析接口返回的 JSON', 'map': '给线程池分配独立任务', 'search': '搜索匹配的引用标号', 'match': '从行首识别标题', 'fullmatch': '判断整个字符串是否为中文', 'findall': '提取全部关键词', 'sub': '去掉 Markdown 标题中的锚点注记', 'removesuffix': '去掉文件后缀', 'startswith': '检查协议、标题或围栏前缀', 'lstrip': '清理标题前缀', 'replace': '更换文档 ID 中的路径分隔符或模型缓存名称', 'items': '遍历映射键值', 'values': '遍历映射值', 'rglob': '列出源代码文件', 'is_file': '检查固定模型缓存是否完整', 'relative_to': '取得项目内的相对路径', 'now': '取得带时区的生成时间', 'isoformat': '生成可审计的时间字符串', 'parse_args': '解析命令行参数', 'add_argument': '声明命令行输入与范围', 'ArgumentParser': '构造脚本参数解析器', 'error': '拒绝错误的评测运行参数', 'platform': '记录测试机器环境', 'include_router': '注册 HTTP 路由', 'exception': '记录失败堆栈便于定位', 'getLogger': '构造模块日志器', 'approx': '按浮点容差比较预期分数', 'raises': '断言非法操作确实抛错', 'setattr': '注入测试替身，不调用付费接口', 'MockTransport': '模拟 HTTP 响应，保留真实 SDK 解析过程', 'Client': '构造 HTTP 客户端', 'Response': '构造测试响应', 'TestClient': '以内存 HTTP 请求验证真实 FastAPI 路由', 'SecretStr': '包装测试用密钥，使配置显示时脱敏', 'snapshot': '按可信身份读取可见片段快照'}.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

## scripts/fetch_code_examples.py

### main（第 24 行）

fetch_bytes 校验 Git Blob；保存原始 Python 资料和 SHA256、来源、权限及引用关系。

内部使用：

- `(PROJECT_ROOT / 'data/corpus/code-examples.json').write_text()`：写入文档或评测报告
- `code_document_id()`：将固定 docs_src Python 示例路径转换为本地文档 ID；拒绝目录穿越与任意 URL。
- `documents.append()`：向列表增加一条记录
- `fetch_bytes()`：GitHub Contents API 下载固定提交；base64 解码并核对 Git Blob SHA1。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `json.dumps()`：把对象序列化为 JSON
- `path.parent.mkdir()`：创建项目数据目录
- `path.relative_to()`：取得项目内的相对路径
- `path.write_bytes()`：保存未经改写的原文或许可证
- `print()`：输出本次脚本运行进度，不输出密钥
- `str()`：转换路径或错误信息为字符串

## scripts/fetch_corpus.py

### fetch_bytes（第 38 行）

GitHub Contents API 下载固定提交；base64 解码并核对 Git Blob SHA1。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `base64.b64decode()`：还原 GitHub Contents API 返回的原文字节
- `hashlib.sha1()`：核对 Git Blob 的内容标识，不用于密码加密
- `hashlib.sha1(blob).hexdigest()`：把摘要转换为十六进制标识
- `httpx.get()`：从官方固定版本接口读取公开文档
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `response.json()`：解析接口返回的 JSON
- `response.raise_for_status()`：拒绝失败的下载，不把错误页面当作资料
- `str()`：转换路径或错误信息为字符串
- `str(len(raw)).encode()`：encode_query 逐条产生测试向量；记录调用数以验证增量跳过。

### fetch（第 51 行）

httpx.get 下载固定提交中的文档；raise_for_status 拒绝失败；SHA256 标记原文。

内部使用：

- `fetch_bytes()`：GitHub Contents API 下载固定提交；base64 解码并核对 Git Blob SHA1。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `output.parent.mkdir()`：创建项目数据目录
- `output.relative_to()`：取得项目内的相对路径
- `output.write_bytes()`：保存未经改写的原文或许可证
- `path.removesuffix()`：去掉文件后缀
- `path.removesuffix('.md').replace()`：复制不可变数据类并更新指定字段
- `print()`：输出本次脚本运行进度，不输出密钥
- `raw.decode()`：把原文字节解码为 UTF-8 文本
- `raw.decode('utf-8').splitlines()`：按原始换行拆分文本
- `raw.decode('utf-8').splitlines()[0].lstrip()`：清理标题前缀
- `raw.decode('utf-8').splitlines()[0].lstrip('# ').split()`：按分隔符切分字符串
- `str()`：转换路径或错误信息为字符串

### main（第 80 行）

ThreadPoolExecutor 下载文档，另存 LICENSE，再写可审计 manifest.json。

内部使用：

- `(PROJECT_ROOT / 'data' / 'corpus' / 'LICENSE.fastapi').write_bytes()`：保存未经改写的原文或许可证
- `(PROJECT_ROOT / 'data' / 'corpus' / 'manifest.json').write_text()`：写入文档或评测报告
- `ThreadPoolExecutor()`：并行下载或执行并发边界测试
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `fetch_bytes()`：GitHub Contents API 下载固定提交；base64 解码并核对 Git Blob SHA1。
- `json.dumps()`：把对象序列化为 JSON
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `pool.map()`：给线程池分配独立任务
- `print()`：输出本次脚本运行进度，不输出密钥

## scripts/ingest.py

### main（第 14 行）

解析目标租户，读取 manifest；SHA256 校验原文；Catalog.upsert 原子入库。

内部使用：

- `(PROJECT_ROOT / 'data' / 'corpus' / 'manifest.json').read_text()`：读取 UTF-8 文本
- `(PROJECT_ROOT / item['file']).read_bytes()`：读取原始字节用于摘要核验
- `DocumentInput()`：构造对象：Pydantic 拒绝额外身份字段，校验 ID、原文长度和来源链接。
- `Principal()`：构造对象：可信身份；dataclass 自动初始化，不从问答正文构造。
- `RAGPipeline()`：构造对象：应用级只读模型对象 + 每请求独立检索快照；不改变共享配置。
- `ValueError()`：表示输入或数据不符合约束
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `counts.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `manifest['documents'].extend()`：批量增加记录
- `parser.add_argument()`：声明命令行输入与范围
- `parser.error()`：拒绝错误的评测运行参数
- `parser.parse_args()`：解析命令行参数
- `pipeline.catalog.upsert()`：chunk_text 分块、encode 算向量，BEGIN IMMEDIATE 原子替换；摘要相同则跳过。
- `print()`：输出本次脚本运行进度，不输出密钥
- `raw.decode()`：把原文字节解码为 UTF-8 文本
- `re.fullmatch()`：判断整个字符串是否为中文
- `supplemental.is_file()`：检查固定模型缓存是否完整
- `supplemental.read_text()`：读取 UTF-8 文本

## scripts/review_server.py

### main（第 11 行）

读取冻结报告及固定原文，建立 ReviewStore，使用 uvicorn 启动本机人工审核。

内部使用：

- `(PROJECT_ROOT / args.dataset).read_bytes()`：读取原始字节用于摘要核验
- `(PROJECT_ROOT / args.report).read_text()`：读取 UTF-8 文本
- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `create_review_app()`：只为本机人工审核注册页面、读取、下载和保存接口，不调用检索或生成模型。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(dataset_raw).hexdigest()`：把摘要转换为十六进制标识
- `json.loads()`：把 JSON 文本解析为结构化对象
- `load_source_documents()`：读取并核对固定语料摘要，加上明确标记的虚构评测资料，供人工展开完整原文。
- `parser.add_argument()`：声明命令行输入与范围
- `parser.error()`：拒绝错误的评测运行参数
- `parser.parse_args()`：解析命令行参数
- `print()`：输出本次脚本运行进度，不输出密钥
- `uvicorn.run()`：在配置的地址启动 HTTP 服务

## scripts/translate_review.py

### is_code（第 15 行）

检测纯代码单元；标识符、命令和代码保持原样，避免翻译改变实际示例。

内部使用：

- `bool()`：把标题匹配结果转换为真或假
- `re.fullmatch()`：判断整个字符串是否为中文
- `re.match()`：从行首识别标题
- `re.search()`：搜索匹配的引用标号
- `re.sub()`：去掉 Markdown 标题中的锚点注记
- `text.startswith()`：检查协议、标题或围栏前缀

### collect_texts（第 26 行）

从陈述、引用和原标注去重收集正文；题目使用独立中文对照，未校验草稿不参加翻译。

内部使用：

- `row.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `set()`：去重，例如被实际使用的引用编号
- `sorted()`：按照指定分数排序并保持可重复的顺序
- `texts.add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `texts.update()`：批量更新当前请求记录或独立配置副本中的字段

### write_cache（第 37 行）

临时写完后原子替换辅助译文缓存，避免工作台读取半份 JSON。

内部使用：

- `NamedTemporaryFile()`：创建仅本次写入使用的临时文件，写完后原子替换评分文件
- `json.dump()`：把真实人工记录序列化写入临时文件，不生成任何评分
- `os.path.isfile()`：检查本次临时译文文件是否还存在，便于安全清理
- `os.replace()`：原子替换本地评分文件，避免只写一半的评分被读取
- `os.unlink()`：清理本次创建的临时译文文件，不删除冻结报告或人工评分
- `path.parent.mkdir()`：创建项目数据目录

### translate_batch（第 57 行）

只请求中文翻译，不回答或判题；核对 ID、中文正文和反引号标识，格式问题最多重做一次。

内部使用：

- `ValueError()`：表示输入或数据不符合约束
- `any()`：检查是否存在匹配值或非零向量分量
- `attempts.append()`：向列表增加一条记录
- `client.chat.completions.create()`：发送带证据的结构化生成请求，读取服务商真实 usage
- `enumerate()`：同时获得条目及位置编号
- `isinstance()`：检查配置对象类型
- `items.items()`：遍历映射键值
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `messages.append()`：向列表增加一条记录
- `print()`：输出本次脚本运行进度，不输出密钥
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `re.findall()`：提取全部关键词
- `re.search()`：搜索匹配的引用标号
- `set()`：去重，例如被实际使用的引用编号
- `str()`：转换路径或错误信息为字符串
- `translated.items()`：遍历映射键值
- `type()`：取得异常类型以记录失败，不输出可能敏感的异常内容

### main（第 114 行）

恢复同一来源的辅助译文，分批翻译并保存；来源问答和真实人工评分始终不修改。

内部使用：

- `(PROJECT_ROOT / 'eval/review_zh_questions.json').read_text()`：读取 UTF-8 文本
- `OpenAI()`：创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型
- `any()`：检查是否存在匹配值或非零向量分量
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `batch.append()`：向列表增加一条记录
- `cache['attempts'].extend()`：批量增加记录
- `cache['texts'].update()`：批量更新当前请求记录或独立配置副本中的字段
- `collect_texts()`：从陈述、引用和原标注去重收集正文；题目使用独立中文对照，未校验草稿不参加翻译。
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `evaluation_settings()`：Settings 读取 RAG 配置；显式开启时 dotenv_values 临时读取工单密钥，不写入文件。
- `hashlib.sha256()`：生成内容、数据集或版本摘要，用于跳过重复计算及追溯
- `hashlib.sha256(raw).hexdigest()`：把摘要转换为十六进制标识
- `hashlib.sha256(source.read_bytes()).hexdigest()`：把摘要转换为十六进制标识
- `is_code()`：检测纯代码单元；标识符、命令和代码保持原样，避免翻译改变实际示例。
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `parser.add_argument()`：声明命令行输入与范围
- `parser.error()`：拒绝错误的评测运行参数
- `parser.parse_args()`：解析命令行参数
- `path.is_file()`：检查固定模型缓存是否完整
- `path.read_text()`：读取 UTF-8 文本
- `print()`：输出本次脚本运行进度，不输出密钥
- `settings.llm_api_key.get_secret_value()`：只在必要调用时取得配置值，不输出密钥
- `source.read_bytes()`：读取原始字节用于摘要核验
- `source.with_name()`：构造同目录的辅助译文路径，不重命名或覆盖原始评测文件
- `translate_batch()`：只请求中文翻译，不回答或判题；核对 ID、中文正文和反引号标识，格式问题最多重做一次。
- `write_cache()`：临时写完后原子替换辅助译文缓存，避免工作台读取半份 JSON。

## scripts/verify_container.py

### docker_call（第 19 行）

subprocess.run 执行参数列表，避免 shell 拼接；错误不回显可能敏感的运行参数。

内部使用：

- `RuntimeError()`：模拟或表示运行阶段的组件故障
- `log.parent.mkdir()`：创建项目数据目录
- `log.write_text()`：写入文档或评测报告
- `result.stdout.strip()`：去掉首尾空白
- `subprocess.run()`：按参数数组运行容器命令，不拼接 shell 命令字符串

### wait_health（第 34 行）

httpx 轮询进程存活，最多三十秒；模型可用性由随后真实问答验证。

内部使用：

- `RuntimeError()`：模拟或表示运行阶段的组件故障
- `client.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `httpx.Client()`：构造 HTTP 客户端
- `time.monotonic()`：读取不受系统时钟校准影响的时间，用于启动截止时间
- `time.sleep()`：短暂等待健康轮询或在测试上游中模拟响应超时

### main（第 48 行）

build 镜像，启动和入库，写测试文档，重建容器后验证原文/检索仍在，再清理测试卷。

内部使用：

- `(PROJECT_ROOT / 'data/corpus/manifest.json').read_text()`：读取 UTF-8 文本
- `Path()`：构造文件路径对象，用于定位项目内源码、数据和报告
- `RuntimeError()`：模拟或表示运行阶段的组件故障
- `SystemExit()`：让验证脚本用非零退出码报告真实失败
- `TemporaryDirectory()`：创建隔离临时目录，退出上下文时清理其文件
- `all()`：检查所有项目或向量值都满足条件
- `any()`：检查是否存在匹配值或非零向量分量
- `argparse.ArgumentParser()`：构造脚本参数解析器
- `asked.json()`：解析接口返回的 JSON
- `asked.json().get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `bool()`：把标题匹配结果转换为真或假
- `cache.is_dir()`：检查模型缓存目录是否存在
- `client.delete()`：检查写权限，execute 删除租户内文档；外键同时清理旧片段。
- `client.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `client.get(base + '/api/documents/' + doc_id, headers=headers).json()`：解析接口返回的 JSON
- `client.post()`：发送测试 POST 请求
- `containers.append()`：向列表增加一条记录
- `containers.remove()`：从本脚本拥有的容器清理清单中移除已删除项
- `datetime.now()`：取得带时区的生成时间
- `datetime.now(UTC).isoformat()`：生成可审计的时间字符串
- `docker_call()`：subprocess.run 执行参数列表，避免 shell 拼接；错误不回显可能敏感的运行参数。
- `env_file.write_text()`：写入文档或评测报告
- `found.json()`：解析接口返回的 JSON
- `httpx.Client()`：构造 HTTP 客户端
- `isinstance()`：检查配置对象类型
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `listed.json()`：解析接口返回的 JSON
- `os.chmod()`：把临时令牌配置文件设置为仅当前用户可读写
- `output.parent.mkdir()`：创建项目数据目录
- `output.write_text()`：写入文档或评测报告
- `parser.add_argument()`：声明命令行输入与范围
- `parser.parse_args()`：解析命令行参数
- `print()`：输出本次脚本运行进度，不输出密钥
- `private_dir.mkdir()`：创建项目数据目录
- `report['checks'].values()`：遍历映射值
- `restored.json()`：解析接口返回的 JSON
- `secrets.token_hex()`：生成容器和卷的随机后缀，避免碰到已有资源
- `secrets.token_urlsafe()`：生成本次容器测试专用高强度令牌，不写入报告
- `shutil.which()`：检查容器命令是否存在，缺少时明确报告无法验证
- `start_container()`：run 创建专用容器，inspect 只读取映射端口，绝不输出容器密钥环境变量。
- `str()`：转换路径或错误信息为字符串
- `sum()`：累计命中数或费用
- `supplements.is_file()`：检查固定模型缓存是否完整
- `supplements.read_text()`：读取 UTF-8 文本
- `time.monotonic()`：读取不受系统时钟校准影响的时间，用于启动截止时间
- `type()`：取得异常类型以记录失败，不输出可能敏感的异常内容
- `wait_health()`：httpx 轮询进程存活，最多三十秒；模型可用性由随后真实问答验证。
- `written.json()`：解析接口返回的 JSON
- `written.raise_for_status()`：检查实际 HTTP 操作是否成功，失败立即停止后续成功断言

### start_container（第 107 行）

run 创建专用容器，inspect 只读取映射端口，绝不输出容器密钥环境变量。

内部使用：

- `containers.append()`：向列表增加一条记录
- `docker_call()`：subprocess.run 执行参数列表，避免 shell 拼接；错误不回显可能敏感的运行参数。
- `json.loads()`：把 JSON 文本解析为结构化对象
- `str()`：转换路径或错误信息为字符串
- `wait_health()`：httpx 轮询进程存活，最多三十秒；模型可用性由随后真实问答验证。

## scripts/write_validation_report.py

### read_report（第 9 行）

read_text 读取已有实测报告；缺少文件时明确返回未运行，绝不补造测试结果。

内部使用：

- `json.loads()`：把 JSON 文本解析为结构化对象
- `path.is_file()`：检查固定模型缓存是否完整
- `path.read_text()`：读取 UTF-8 文本

### case_details（第 15 行）

把问题、回答、助手意见和各条证据整理成可展开段落，人工可按原文逐项复核。

内部使用：

- `'\n'.join()`：连接字符串片段
- `evidence['quote'].splitlines()`：按原始换行拆分文本
- `lines.append()`：向列表增加一条记录
- `lines.extend()`：批量增加记录
- `next()`：从迭代器获取首个结果或指定默认值
- `review.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `row.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分

### main（第 52 行）

读取问答、并发和容器报告，计算实际分母并生成中文总览及逐题证据索引。

内部使用：

- `'\n'.join()`：连接字符串片段
- `Counter()`：统计每个词出现在多少片段中
- `answers.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `case_details()`：把问题、回答、助手意见和各条证据整理成可展开段落，人工可按原文逐项复核。
- `container.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `container.get('checks', {}).items()`：遍历映射键值
- `groups.items()`：遍历映射键值
- `hard.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `labels.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `lines.append()`：向列表增加一条记录
- `lines.extend()`：批量增加记录
- `path.write_text()`：写入文档或评测报告
- `print()`：输出本次脚本运行进度，不输出密钥
- `r.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `r.get('assistant_review', {}).get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `read_report()`：read_text 读取已有实测报告；缺少文件时明确返回未运行，绝不补造测试结果。
- `report.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `report.get('concurrency', {}).items()`：遍历映射键值
- `successes.values()`：遍历映射值
- `sum()`：累计命中数或费用

## tests/conftest.py

### encode（第 18 行）

encode_query 逐条产生测试向量；记录调用数以验证增量跳过。

内部使用：

- `np.array()`：构造数值数组
- `self.encode_query()`：按 alpha/beta/gamma 生成固定向量并归一化，便于精确断言权限过滤结果。

### encode_query（第 23 行）

按 alpha/beta/gamma 生成固定向量并归一化，便于精确断言权限过滤结果。

内部使用：

- `float()`：把 NumPy 分数转换为可序列化数值
- `np.array()`：构造数值数组
- `np.linalg.norm()`：计算向量长度，用于 L2 归一化
- `text.lower()`：把文本统一成小写以分词匹配
- `vector.any()`：检查是否存在匹配值或非零向量分量

### rerank（第 34 行）

切片保留调用方要求数量；真实重排模型通过独立 benchmark 验证。

内部使用：

- 无额外函数调用。

### pipeline（第 40 行）

Settings 指向临时库，RAGPipeline 注入测试组件，隔离真实知识库。

内部使用：

- `FakeEmbedder()`：构造对象：仅用于逻辑测试，不参与真实模型评测。
- `PassReranker()`：构造对象：仅用于逻辑测试的稳定重排替身。
- `RAGPipeline()`：构造对象：应用级只读模型对象 + 每请求独立检索快照；不改变共享配置。
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。

### review_paths（第 47 行）

建立一题合成报告，其中 AI 结论故意不可信，用于验证审核页面不暴露预评分。

内部使用：

- `json.dumps()`：把对象序列化为 JSON
- `source.write_text()`：写入文档或评测报告

## tests/test_answer_repairs.py

### test_numbered_quote_preserves_markdown（第 19 行）

模型只选 ID，resolve_references 必须还原包括链接和反引号的精确原文。

内部使用：

- `SelectedDraft.model_validate()`：校验编号引用测试数据，拒绝多余字段或超出预算的列表
- `evidence_spans()`：按空行及长度切出原文子串，不改写内容；剔除占位指令，单个引用不超过 800 字符。
- `resolve_references()`：将有效片段/单元 ID 还原成服务器已有 quote；拒绝不存在的任意编号。

### test_every_span_is_original_substring（第 45 行）

长段和空白分割之后仍然引用实际子串，编号唯一且最长 800 字符。

内部使用：

- `all()`：检查所有项目或向量值都满足条件
- `evidence_spans()`：按空行及长度切出原文子串，不改写内容；剔除占位指令，单个引用不超过 800 字符。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入
- `range()`：生成用于分段、重复实验或遍历的整数序列

### test_model_cannot_write_quote_or_exceed_claim_limit（第 52 行）

SelectedDraft 拒绝 quote 字段及九条陈述；限制必须在提示词和校验器中一致。

内部使用：

- `SelectedDraft.model_validate()`：校验编号引用测试数据，拒绝多余字段或超出预算的列表
- `pytest.raises()`：断言非法操作确实抛错

### test_multiple_valid_spans_do_not_fail_old_three_reference_limit（第 62 行）

TestClient 复现中四个有效单元被旧上限误拒；保留全部证据并仍拒绝超过八个引用。

内部使用：

- `SelectedDraft.model_validate()`：校验编号引用测试数据，拒绝多余字段或超出预算的列表
- `evidence_spans()`：按空行及长度切出原文子串，不改写内容；剔除占位指令，单个引用不超过 800 字符。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pytest.raises()`：断言非法操作确实抛错
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `resolve_references()`：将有效片段/单元 ID 还原成服务器已有 quote；拒绝不存在的任意编号。

### test_original_wrong_languages_are_detected（第 93 行）

用原失败回答及相同语句检查实际文本，不相信模型自行声明 language=en。

内部使用：

- `check_language()`：移除代码和 URL 后识别正文；短技术表达记为不确定，高置信度外语判不匹配。
- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入

### test_code_does_not_count_as_answer_language（第 99 行）

正文英文中的中文代码注释不触发语言误报；显式语言可覆盖自动判断。

内部使用：

- `answer_language()`：检查显式 en/zh/auto；自动模式对含中文的本项目问题选择中文，否则英文。
- `check_language()`：移除代码和 URL 后识别正文；短技术表达记为不确定，高置信度外语判不匹配。

### test_context_expansion_keeps_threshold_and_acl（第 111 行）

低分邻居由可靠锚点补充，私有代码不进入读者快照；没有锚点时不扩大上下文。

内部使用：

- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `any()`：检查是否存在匹配值或非零向量分量
- `code_document_id()`：将固定 docs_src Python 示例路径转换为本地文档 ID；拒绝目录穿越与任意 URL。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `select_context()`：先筛可靠锚点，再从同一权限快照添加其代码引用与相邻片段；记录每次选择原因。

### test_inline_code_lookup_cannot_read_hidden_doc（第 129 行）

公开文档指向私有示例时，select_context 只能从已授权快照查找，不能越权补全。

内部使用：

- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `all()`：检查所有项目或向量值都满足条件
- `code_document_id()`：将固定 docs_src Python 示例路径转换为本地文档 ID；拒绝目录穿越与任意 URL。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `select_context()`：先筛可靠锚点，再从同一权限快照添加其代码引用与相邻片段；记录每次选择原因。

### test_exact_code_identifiers_work_without_semantic_anchor（第 142 行）

英文模型没有高分时，显式 get_db/yield/finally 可找真实代码；仍然只用可见快照。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `any()`：检查是否存在匹配值或非零向量分量
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `select_context()`：先筛可靠锚点，再从同一权限快照添加其代码引用与相邻片段；记录每次选择原因。

### test_review_detects_forbidden_uncited_context（第 161 行）

模型收到未引用的私有片段也应判越权；评测不能只检查最终回答和原始召回。

内部使用：

- `mechanical_review()`：检查状态、候选及实际模型上下文的权限与合成标记；字串检查不能代替语义评审。

### test_server_repairs_once_and_counts_all_usage（第 176 行）

真实 SDK 首轮收到未知 span ID，第二轮正确；次数固定两次且累计两轮 usage。

内部使用：

- `Generator()`：构造对象：默认摘录；compatible 使用编号引用、语言检查与最多一次内容纠正。
- `Generator(settings).generate()`：确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。
- `OpenAI()`：创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型
- `SecretStr()`：包装测试用密钥，使配置显示时脱敏
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `httpx.Client()`：构造 HTTP 客户端
- `httpx.MockTransport()`：模拟 HTTP 响应，保留真实 SDK 解析过程
- `httpx.Response()`：构造测试响应
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `monkeypatch.setattr()`：注入测试替身，不调用付费接口
- `requests.append()`：向列表增加一条记录

### reply（第 180 行）

记录 SDK 消息并按轮次返回不同编号；这是协议测试，不冒充真实质量评测。

内部使用：

- `httpx.Response()`：构造测试响应
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `requests.append()`：向列表增加一条记录

### test_claims_are_not_language_certificate（第 229 行）

模型声明 en 但正文西班牙语时，两轮仍失败，系统不得显示为回答成功。

内部使用：

- `Generator()`：构造对象：默认摘录；compatible 使用编号引用、语言检查与最多一次内容纠正。
- `Generator(Settings(llm_provider='compatible', llm_api_key=SecretStr('synthetic'), _env_file=None)).generate()`：确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。
- `OpenAI()`：创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型
- `SecretStr()`：包装测试用密钥，使配置显示时脱敏
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `calls.append()`：向列表增加一条记录
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `httpx.Client()`：构造 HTTP 客户端
- `httpx.MockTransport()`：模拟 HTTP 响应，保留真实 SDK 解析过程
- `httpx.Response()`：构造测试响应
- `json.dumps()`：把对象序列化为 JSON
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `monkeypatch.setattr()`：注入测试替身，不调用付费接口

### reply（第 233 行）

固定返回错误语言，验证纠正上限和不伪造成功。

内部使用：

- `calls.append()`：向列表增加一条记录
- `httpx.Response()`：构造测试响应
- `json.dumps()`：把对象序列化为 JSON

## tests/test_boundaries.py

### add（第 20 行）

DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。

内部使用：

- `DocumentInput()`：构造对象：Pydantic 拒绝额外身份字段，校验 ID、原文长度和来源链接。
- `pipeline.catalog.upsert()`：chunk_text 分块、encode 算向量，BEGIN IMMEDIATE 原子替换；摘要相同则跳过。

### test_incremental_skips_embedding（第 35 行）

重复 upsert 不调用 encode；摘要未变化时没有重复片段。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。

### test_update_removes_old_chunks（第 45 行）

upsert 替换版本后 snapshot 只有新原文和新版本。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。

### test_failed_embedding_preserves_version（第 56 行）

替换 encode 使其抛错；upsert 失败后 snapshot 保持原文。

内部使用：

- `RuntimeError()`：模拟或表示运行阶段的组件故障
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `pytest.raises()`：断言非法操作确实抛错

### fail（第 60 行）

测试故障注入：模拟模型不可用。

内部使用：

- `RuntimeError()`：模拟或表示运行阶段的组件故障

### test_nonfinite_embedding_rejected（第 75 行）

encode 返回 NaN 时 upsert 拒绝写入，documents 仍为空。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `np.array()`：构造数值数组
- `pipeline.catalog.documents()`：_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。
- `pytest.raises()`：断言非法操作确实抛错

### test_changed_model_rejected（第 83 行）

修改 fingerprint 后 snapshot 和 upsert 都拒绝混合模型。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `pytest.raises()`：断言非法操作确实抛错

### test_delete_cascades（第 93 行）

Catalog.delete 后 snapshot 不再检索到该文档片段。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pipeline.catalog.delete()`：检查写权限，execute 删除租户内文档；外键同时清理旧片段。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。

### test_acl_before_retrieval（第 101 行）

高相关 ops 片段不进入读者快照；retrieve 始终命中可见 public 片段。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `pipeline.retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。
- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入

### test_department_reader（第 110 行）

snapshot 给 ops 身份运维资料，普通读者不可见。

内部使用：

- `Principal()`：构造对象：可信身份；dataclass 自动初始化，不从问答正文构造。
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pipeline.catalog.documents()`：_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。

### test_tenant_isolation_even_admin（第 118 行）

Catalog.snapshot 对管理员仍执行租户过滤。

内部使用：

- `Principal()`：构造对象：可信身份；dataclass 自动初始化，不从问答正文构造。
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。

### test_acl_metadata_change_invalidates_revision（第 124 行）

把 public 改为 ops 时 upsert 改版，读者立即失去资料可见性。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `pipeline.catalog.documents()`：_scope 限制可见文档；列表返回元信息，指定 ID 时返回原文。

### test_reader_cannot_write（第 132 行）

直接调用 Catalog 写方法也会检查 admin，而非只依靠 HTTP 路由。

内部使用：

- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `pipeline.catalog.delete()`：检查写权限，execute 删除租户内文档；外键同时清理旧片段。
- `pytest.raises()`：断言非法操作确实抛错

### test_heading_line_metadata（第 140 行）

chunk_text 保留章节和原始行号，不跨标题重叠。

内部使用：

- `chunk_text()`：get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。

### test_chunk_bounds_and_empty（第 149 行）

chunk_text 拆长行且保持字符上限；空输入没有片段，非法 overlap 拒绝。

内部使用：

- `all()`：检查所有项目或向量值都满足条件
- `chunk_text()`：get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pytest.raises()`：断言非法操作确实抛错

### test_code_heading_is_not_section（第 157 行）

chunk_text 不把代码围栏里的 # 注释当作 Markdown 标题。

内部使用：

- `chr()`：按字符编码取得代码围栏标记
- `chunk_text()`：get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。
- `len()`：统计字符数或条目数；这里不是 Token 计数器

### test_technical_and_cjk_tokens（第 163 行）

_tokenize 保留技术标识符，并拆分中文而非当成一个长单词。

内部使用：

- `_tokenize()`：re.findall 保留技术标识符；中文切为字和二元组；过滤常见英文虚词。

### test_rrf_real_cosine_score（第 169 行）

HybridRetriever 返回真实余弦而不是通道排名；dense_search 确保可解释性。

内部使用：

- `HybridRetriever()`：构造对象：仅处理 Catalog 已过滤权限的快照，不能接触不可见文档。
- `HybridRetriever(store, pipeline.embedder).retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `pipeline.catalog.snapshot()`：_scope 在检索前过滤权限；恢复 Chunk 和向量；不可见资料不进入 BM25/向量检索。
- `pytest.approx()`：按浮点容差比较预期分数

### test_dense_tie_is_stable（第 178 行）

dense_search 同分时维持索引顺序；非法 k 被拒绝。

内部使用：

- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `VectorStore()`：构造对象：单次请求的可见文档快照，不共享可变排名和 top_k。
- `np.array()`：构造数值数组
- `pytest.raises()`：断言非法操作确实抛错
- `store.add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `store.dense_search()`：矩阵乘法算余弦；稳定 argsort 在同分时保持快照顺序。

### evidence_result（第 187 行）

RetrievalResult 构造可核验的固定引用材料。

内部使用：

- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。

### test_invalid_citations_rejected（第 202 行）

validate_draft 拒绝越界 ID、伪造原文与纯空白摘录。

内部使用：

- `Claim()`：构造对象：还原后的陈述和原文证据；Pydantic 拒绝额外字段。
- `Draft()`：构造对象：还原后的完整回答；空列表代表证据不足。
- `Evidence()`：构造对象：服务端还原后的引用；原文必须来自本次证据，保持旧验证接口可读。
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入
- `pytest.raises()`：断言非法操作确实抛错
- `validate_draft()`：检查还原引用的范围及原文子串；字串存在不能代替语义支持关系评审。

### test_only_used_citations_returned（第 209 行）

validate_draft 仅返回陈述使用的引用，不把所有检索候选视为引用。

内部使用：

- `Claim()`：构造对象：还原后的陈述和原文证据；Pydantic 拒绝额外字段。
- `Draft()`：构造对象：还原后的完整回答；空列表代表证据不足。
- `Evidence()`：构造对象：服务端还原后的引用；原文必须来自本次证据，保持旧验证接口可读。
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `validate_draft()`：检查还原引用的范围及原文子串；字串存在不能代替语义支持关系评审。

### test_inline_citation_cannot_be_invented（第 219 行）

validate_draft 不接受模型在正文插入额外引用标号。

内部使用：

- `Claim()`：构造对象：还原后的陈述和原文证据；Pydantic 拒绝额外字段。
- `Draft()`：构造对象：还原后的完整回答；空列表代表证据不足。
- `Evidence()`：构造对象：服务端还原后的引用；原文必须来自本次证据，保持旧验证接口可读。
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `pytest.raises()`：断言非法操作确实抛错
- `validate_draft()`：检查还原引用的范围及原文子串；字串存在不能代替语义支持关系评审。

### test_empty_evidence_abstains（第 232 行）

Generator 在无证据时拒答，且不返回引用和伪造 Token 使用量。

内部使用：

- `Generator()`：构造对象：默认摘录；compatible 使用编号引用、语言检查与最多一次内容纠正。
- `Generator(Settings(_env_file=None)).generate()`：确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。

### test_parallel_requests_keep_own_topk（第 238 行）

并行 retrieve 的 top_k 互不影响，参数不写入共享 settings。

内部使用：

- `ThreadPoolExecutor()`：并行下载或执行并发边界测试
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `list()`：把迭代结果收集为列表
- `pipeline.retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。
- `pool.map()`：给线程池分配独立任务
- `range()`：生成用于分段、重复实验或遍历的整数序列
- `str()`：转换路径或错误信息为字符串

### run（第 243 行）

retrieve 用请求自己的 k 检索；返回实际结果数量。

内部使用：

- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `pipeline.retrieve()`：dense_search 与 BM25.get_scores 召回；混合模式按排名倒数 RRF 融合。

### test_http_auth_and_body（第 252 行）

TestClient 验证认证、越权、客户端自报身份与 top_k 范围边界。

内部使用：

- `TestClient()`：以内存 HTTP 请求验证真实 FastAPI 路由
- `add()`：DocumentInput 构造文档，Catalog.upsert 使用测试向量入库。
- `client.delete()`：检查写权限，execute 删除租户内文档；外键同时清理旧片段。
- `client.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `client.get('/api/documents', headers=reader).json()`：解析接口返回的 JSON
- `client.post()`：发送测试 POST 请求
- `client.post('/api/ask', headers=reader, json={'question': 'alpha'}).json()`：解析接口返回的 JSON
- `create_app()`：token_map 校验认证配置，RAGPipeline 初始化目录，include_router 注册接口。

### test_nonlocal_demo_auth_rejected（第 278 行）

token_map 对非本机地址拒绝默认演示令牌。

内部使用：

- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `pytest.raises()`：断言非法操作确实抛错
- `token_map()`：读取服务端令牌与身份映射，正文不能指定权限

### test_metric_requires_relevant_passage（第 284 行）

evidence_metrics 即使找到同一文档但缺少答案段落，也不得计为命中。

内部使用：

- `Chunk()`：构造对象：一个可追溯片段；source 是文档 ID，原始行号从 1 开始。
- `RetrievalResult()`：构造对象：一条候选证据；score 是当前排名分数，各检索通道分数单独保存。
- `evidence_metrics()`：按文档 ID + 原文摘录判定命中，计算证据覆盖率、Any/All-Gold@K 和 MRR。

### test_multievidence_metrics（第 291 行）

evidence_metrics 只找齐一半资料时 coverage 为 1/2，All-Gold 为 0。

内部使用：

- `evidence_metrics()`：按文档 ID + 原文摘录判定命中，计算证据覆盖率、Any/All-Gold@K 和 MRR。
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。

### test_chunk_id_stable（第 303 行）

chunk_text 的相同原文生成相同 ID，不同内容生成不同 ID。

内部使用：

- `chunk_text()`：get_settings 取默认大小；按标题和行分块；replace 补充稳定 ID。

## tests/test_generation.py

### test_sdk_response_validation（第 34 行）

MockTransport 模拟模型响应；真实 SDK 解析，Generator 校验引用并保留真实 usage。

内部使用：

- `Generator()`：构造对象：默认摘录；compatible 使用编号引用、语言检查与最多一次内容纠正。
- `Generator(settings).generate()`：确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。
- `OpenAI()`：创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型
- `SecretStr()`：包装测试用密钥，使配置显示时脱敏
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `httpx.Client()`：构造 HTTP 客户端
- `httpx.MockTransport()`：模拟 HTTP 响应，保留真实 SDK 解析过程
- `httpx.Response()`：构造测试响应
- `json.loads()`：把 JSON 文本解析为结构化对象
- `monkeypatch.setattr()`：注入测试替身，不调用付费接口
- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入

### reply（第 37 行）

读取实际请求格式并返回符合服务商协议的响应。

内部使用：

- `httpx.Response()`：构造测试响应
- `json.loads()`：把 JSON 文本解析为结构化对象

## tests/test_human_review.py

### synthetic_score（第 12 行）

生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

内部使用：

- `HumanScore()`：构造对象：只能提交明确的人工判断；任务成功由程序汇总，不能自报成功或审核身份类别。

### test_initial_scores_empty_and_ai_grades_hidden（第 28 行）

初始化不把 AI 通过结论转成人工评分；全量成功率待填且来源原字节不变。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `json.dumps()`：把对象序列化为 JSON
- `source.read_bytes()`：读取原始字节用于摘要核验
- `store.export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `store.material()`：读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。

### test_saved_score_survives_restart_and_author_not_external（第 42 行）

显式输入写盘后可恢复，作者计数与第三方计数分开；原评测报告保持不变。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `ReviewStore(source, output).export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `source.read_bytes()`：读取原始字节用于摘要核验
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### test_failure_requires_notes_and_remains_in_denominator（第 58 行）

有未支持陈述必须保留具体原因，失败仍计入总数，不提高分数。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `pytest.raises()`：断言非法操作确实抛错
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### test_boolean_scores_not_coerced（第 72 行）

不把字符串或数字强制转换为人工通过；审核参数需要真实布尔值。

内部使用：

- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入
- `pytest.raises()`：断言非法操作确实抛错
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### test_support_not_applicable_only_for_no_answer（第 78 行）

回答题必须判断支持关系，拒答允许不适用；字段适用性由真实状态决定。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `output.unlink()`：清理本次临时文件或临时测试文件，不删除原评测报告
- `pytest.raises()`：断言非法操作确实抛错
- `source.read_text()`：读取 UTF-8 文本
- `source.write_text()`：写入文档或评测报告
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### test_unknown_case_and_changed_source_cannot_save（第 96 行）

非法题号和冻结来源变化都不能写入评分，不把旧评分绑定到新答案。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `output.read_bytes()`：读取原始字节用于摘要核验
- `pytest.raises()`：断言非法操作确实抛错
- `source.read_text()`：读取 UTF-8 文本
- `source.write_text()`：写入文档或评测报告
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### test_disk_failure_restores_unsaved_state（第 109 行）

模拟写盘失败，内存和文件都保持待审，不能向界面声称已经保存。

内部使用：

- `OSError()`：测试中模拟磁盘写入失败，用于验证不能谎称评分已保存
- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `monkeypatch.setattr()`：注入测试替身，不调用付费接口
- `output.read_bytes()`：读取原始字节用于摘要核验
- `pytest.raises()`：断言非法操作确实抛错
- `store.export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### fail（第 115 行）

仅临时测试中的故障注入，不修改真实评分。

内部使用：

- `OSError()`：测试中模拟磁盘写入失败，用于验证不能谎称评分已保存

### test_origin_boundary_for_manual_save（第 126 行）

跨网站和缺少手动操作头的请求拒绝；同源明确人工输入仅保存到临时评分文件。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `TestClient()`：以内存 HTTP 请求验证真实 FastAPI 路由
- `client.get()`：安全读取映射键或发送测试 GET 请求，依所属对象区分
- `client.get('/api/export').json()`：解析接口返回的 JSON
- `client.post()`：发送测试 POST 请求
- `create_review_app()`：只为本机人工审核注册页面、读取、下载和保存接口，不调用检索或生成模型。
- `store.export()`：下载已经保存的真实人工评分，待审项不补写为成功。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。
- `synthetic_score().model_dump()`：导出已经通过 Pydantic 验证的文档字段

### test_complete_scope_and_separate_output_required（第 151 行）

没跑完不能建立全量审核，评分不能覆盖原报告，作者与第三方记录不能混用。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `pytest.raises()`：断言非法操作确实抛错
- `source.read_text()`：读取 UTF-8 文本
- `source.write_text()`：写入文档或评测报告
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

### test_manual_pass_cannot_override_execution_boundary（第 167 行）

人工勾选不能掩盖模型越权或错误执行，完整任务成功还受实际边界条件约束。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `json.dumps()`：把对象序列化为 JSON
- `json.loads()`：把 JSON 文本解析为结构化对象
- `source.read_text()`：读取 UTF-8 文本
- `source.write_text()`：写入文档或评测报告
- `store.save()`：要求同源和手动操作标记，调用 save；非法题号或不完整评分不能写入。
- `synthetic_score()`：生成临时协议测试的显式评分；这些值不是人类对真实评测题目的评分。

## tests/test_reliability.py

### test_sdk_fault_has_code_and_no_retry（第 27 行）

MockTransport 注入错误，真实 SDK 必须只请求一次且 Generator 转换稳定错误码。

内部使用：

- `Generator()`：构造对象：默认摘录；compatible 使用编号引用、语言检查与最多一次内容纠正。
- `OpenAI()`：创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型
- `SecretStr()`：包装测试用密钥，使配置显示时脱敏
- `Settings()`：构造对象：BaseSettings 解析 RAG_ 环境变量；Field 校验范围。
- `calls.append()`：向列表增加一条记录
- `evidence_result()`：RetrievalResult 构造可核验的固定引用材料。
- `generator.generate()`：确定语言，构造原文编号；还原并核验引用与正文语言，必要时有限纠正，累加 usage。
- `httpx.Client()`：构造 HTTP 客户端
- `httpx.ConnectError()`：故障注入中模拟连接失败，不读取真实密钥
- `httpx.MockTransport()`：模拟 HTTP 响应，保留真实 SDK 解析过程
- `httpx.ReadTimeout()`：故障注入中模拟读取超时，验证分类回包和零自动重试
- `httpx.Response()`：构造测试响应
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `monkeypatch.setattr()`：注入测试替身，不调用付费接口
- `pytest.mark.parametrize()`：让同一个边界测试覆盖多个模式或错误输入
- `pytest.raises()`：断言非法操作确实抛错

### reply（第 31 行）

记录调用次数，返回指定状态或抛出 HTTP 网络异常。

内部使用：

- `calls.append()`：向列表增加一条记录
- `httpx.ConnectError()`：故障注入中模拟连接失败，不读取真实密钥
- `httpx.ReadTimeout()`：故障注入中模拟读取超时，验证分类回包和零自动重试
- `httpx.Response()`：构造测试响应

### test_failure_releases_capacity（第 54 行）

首请求抛出超时后第二请求成功，证明 finally.release 不会永久占住执行名额。

内部使用：

- `GenerationUnavailable()`：构造对象：上游故障分类；网络错误不会触发内容纠正重试。
- `TestClient()`：以内存 HTTP 请求验证真实 FastAPI 路由
- `calls.append()`：向列表增加一条记录
- `client.post()`：发送测试 POST 请求
- `create_app()`：token_map 校验认证配置，RAGPipeline 初始化目录，include_router 注册接口。
- `first.json()`：解析接口返回的 JSON
- `len()`：统计字符数或条目数；这里不是 Token 计数器

### query（第 58 行）

首轮故障、下一轮恢复，验证接口会释放名额并如实回包。

内部使用：

- `GenerationUnavailable()`：构造对象：上游故障分类；网络错误不会触发内容纠正重试。
- `calls.append()`：向列表增加一条记录
- `len()`：统计字符数或条目数；这里不是 Token 计数器

### test_over_capacity_fails_fast（第 77 行）

Event 持住首请求；第二请求返回 QUERY_CAPACITY，完成后新请求可以执行。

内部使用：

- `Event()`：创建测试线程之间的开始和释放信号
- `TestClient()`：以内存 HTTP 请求验证真实 FastAPI 路由
- `Thread()`：构造测试服务或并发请求的后台线程
- `busy.json()`：解析接口返回的 JSON
- `client.post()`：发送测试 POST 请求
- `create_app()`：token_map 校验认证配置，RAGPipeline 初始化目录，include_router 注册接口。
- `entered.set()`：去重，例如被实际使用的引用编号
- `entered.wait()`：测试等待首请求进入执行阶段；有两秒超时保护
- `release.set()`：去重，例如被实际使用的引用编号
- `release.wait()`：故障测试中等待释放信号；超时会使测试失败
- `thread.join()`：连接字符串片段
- `thread.start()`：启动当前实验的后台线程

### query（第 81 行）

仅用于占满测试名额；Event 通知主线程，不让等待超过两秒。

内部使用：

- `entered.set()`：去重，例如被实际使用的引用编号
- `release.wait()`：故障测试中等待释放信号；超时会使测试失败

### test_boundary_score_checks_retrieved_not_only_citations（第 107 行）

mechanical_review 即使未引用私有候选，也必须把越权检索判为失败。

内部使用：

- `mechanical_review()`：检查状态、候选及实际模型上下文的权限与合成标记；字串检查不能代替语义评审。

## tests/test_review_translation.py

### test_code_and_partial_docker_snippets_unchanged（第 12 行）

纯代码、URL 和半个 Docker 围栏不强制加中文；自然语言说明仍参加翻译。

内部使用：

- `is_code()`：检测纯代码单元；标识符、命令和代码保持原样，避免翻译改变实际示例。

### test_only_visible_claims_quotes_and_labels_translated（第 20 行）

去重陈述和证据；未校验草稿、AI 评分和人工评分不进入翻译输入。

内部使用：

- `collect_texts()`：从陈述、引用和原标注去重收集正文；题目使用独立中文对照，未校验草稿不参加翻译。

### test_translation_ids_and_identifiers_checked（第 37 行）

首轮改动标识符会被拒，第二轮保留代码后接受；不是模型质量评测。

内部使用：

- `SimpleNamespace()`：构造仅测试使用的合成协议对象，不调用模型，不写真实人工评分
- `calls.append()`：向列表增加一条记录
- `json.dumps()`：把对象序列化为 JSON
- `len()`：统计字符数或条目数；这里不是 Token 计数器
- `translate_batch()`：只请求中文翻译，不回答或判题；核对 ID、中文正文和反引号标识，格式问题最多重做一次。

### create（第 41 行）

合成翻译协议响应，明确记录两次请求，不读取真实密钥。

内部使用：

- `SimpleNamespace()`：构造仅测试使用的合成协议对象，不调用模型，不写真实人工评分
- `calls.append()`：向列表增加一条记录
- `json.dumps()`：把对象序列化为 JSON
- `len()`：统计字符数或条目数；这里不是 Token 计数器

### test_reading_translation_does_not_replace_evaluation_or_scores（第 61 行）

中文显示材料单独加载，原英文和空人工记录都保持原字节与真实来源。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `json.dumps()`：把对象序列化为 JSON
- `source.read_bytes()`：读取原始字节用于摘要核验
- `source.with_name()`：构造同目录的辅助译文路径，不重命名或覆盖原始评测文件
- `source.with_name(source.stem + '.zh.json').write_text()`：写入文档或评测报告
- `store.material()`：读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。

### test_translation_must_match_frozen_source（第 83 行）

另一份报告的译文不能套到当前题目，以免审核错误的答案版本。

内部使用：

- `ReviewStore()`：构造对象：冻结评测结果与评分文件分开；不预填答案评分，不覆盖原始评测报告。
- `json.dumps()`：把对象序列化为 JSON
- `pytest.raises()`：断言非法操作确实抛错
- `source.with_name()`：构造同目录的辅助译文路径，不重命名或覆盖原始评测文件
- `source.with_name(source.stem + '.zh.json').write_text()`：写入文档或评测报告
- `store.material()`：读取隐藏 AI 结论的审核材料；冻结来源发生变化时明确拒绝继续评分。

## 前端函数

- `api()`：fetch 携带访问令牌请求同源 API；json 解析结果；失败抛 Error。
- `loadDocs()`：api 获取文档；createElement 建列表；textContent 安全显示标题。
- `ask()`：api 发问答请求；createElement 构造引用；toFixed 格式化耗时。
- `$()`：document.getElementById 按页面元素 ID 找到控件。

## 新增官方资料示例中的函数

这些文件是知识库资料，未作为业务模块执行；原文保持 MIT 官方版本。
- 数据库示例 `get_db()`：调用 DBSession() 创建会话，yield 交给使用方，
  在 finally 调用 db.close()。DBSession 由应用配置，示例没有定义它。
- TestClient 示例 `read_main()`：返回固定问候数据，无内部函数调用。
- `test_read_main()`：client.get() 请求接口，response.json() 读取响应，
  检查状态和内容。模块用 FastAPI() 创建应用、TestClient(app) 创建客户端。

## 人工复核页面函数（eval/review_ui.html）

以下只操作人工输入和本地评分接口，完全不调用大模型。

| 函数 | 当前功能与内部调用 |
|---|---|
| el | document.getElementById 按固定 ID 找控件，是简短箭头函数 |
| api | fetch 请求同源接口，response.json 解析数据；Error 表示真实失败 |
| node | document.createElement 建节点，textContent 安全显示原文，不执行原文 HTML |
| text | el 找控件，用 textContent 设置显示文字 |
| setMessage | text 显示真实保存结果，classList.toggle 设置错误样式 |
| visibleCases | el 读取筛选，map 配对题目与位置，filter 按实际人工记录筛选 |
| renderProgress | text 与 style 更新进度；只读取服务端人工统计，未审完不显示全量率 |
| renderGrid | visibleCases 取得列表，node 创建按钮，classList 根据已保存人工结果着色；点击调用 go |
| appendSource | node 展示出处，split/map/join 保留原文行号；仅为 HTTP(S) 网址创建链接 |
| renderEvidence | find 配对陈述与引用，node 展示原文，appendSource 展开完整文档；同时显示实际上下文与原标注 |
| renderFields | node 建五项选择，恢复之前的真实人工值；onchange 只标记未保存，没有自动评分 |
| renderCase | text 设置本题信息，调用 renderEvidence、renderFields、renderGrid、renderProgress |
| go | confirm 提醒未保存修改；renderCase 切题，window.scrollTo 回到顶部 |
| adjacent | visibleCases 与 findIndex 找当前题的位置，go 切换当前筛选中的上一／下一题 |
| collectScore | el 读取人工选择，some 检查失败项，Error 拒绝空白判断或缺少失败原因 |
| saveScore | collectScore 校验输入，api 发手动保存请求；成功后 renderCase 刷新，findIndex 寻找待审题；setMessage 报告失败 |
| load | api 读冻结材料，localStorage.getItem 恢复称呼，findIndex 选择待审题，renderCase 展示 |
| tr | 读取绑定同一来源的中文辅助译文，不改变原始评测或评分 |
| appendOriginal | node 与 createElement 创建可展开的英文原记录，供核对译文 |
| translatedAnswer | tr 翻译显示陈述，Set 去重原有引用；map/join 组合阅读文本 |

页面事件回调：保存按钮调用 saveScore；导航调用 adjacent；筛选调用 visibleCases/go；
备注输入只设置 dirty。提交表单时 preventDefault 避免意外刷新；
beforeunload 在未保存时提示。匿名回调没有任何自动选通过或调用模型的步骤。
