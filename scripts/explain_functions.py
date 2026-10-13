"""从源码生成中文函数阅读索引；源码 docstring 描述职责，AST 列出内部调用。"""

import ast
from pathlib import Path

from app.config import PROJECT_ROOT

GLOSSARY = {
    "with_name": "构造同目录的辅助译文路径，不重命名或覆盖原始评测文件",
    "SimpleNamespace": "构造仅测试使用的合成协议对象，不调用模型，不写真实人工评分",
    "os.path.isfile": "检查本次临时译文文件是否还存在，便于安全清理",
    "os.unlink": "清理本次创建的临时译文文件，不删除冻结报告或人工评分",
    "HumanScore.model_validate": "校验恢复的评分需要明确布尔判断，拒绝用字符串或数字冒充人工通过",
    "resolve": "取得规范绝对路径，用于防止评分文件覆盖原报告",
    "NamedTemporaryFile": "创建仅本次写入使用的临时文件，写完后原子替换评分文件",
    "file.write": "写入评分文件的结尾换行，不调用外部服务",
    "json.dump": "把真实人工记录序列化写入临时文件，不生成任何评分",
    "os.replace": "原子替换本地评分文件，避免只写一半的评分被读取",
    "unlink": "清理本次临时文件或临时测试文件，不删除原评测报告",
    "KeyError": "拒绝不存在的评测题号，不能保存额外或伪造记录",
    "pop": "写盘失败时撤回未保存的内存评分，恢复原有状态",
    "JSONResponse": "返回真实人工记录的 JSON，不把待审核项补成通过",
    "OSError": "测试中模拟磁盘写入失败，用于验证不能谎称评分已保存",
    "removeprefix": "去掉固定路径前缀，不执行文件访问",
    "abs": "计算片段编号距离，只扩展紧邻的前后片段",
    "dict.fromkeys": "按出现顺序去重代码引用路径",
    "sort": "按明确规则排序本次候选，不修改全局索引",
    "SelectedDraft.model_validate_json": "校验模型只能提交语言、陈述和合法格式的编号引用",
    "SelectedDraft.model_validate": "校验编号引用测试数据，拒绝多余字段或超出预算的列表",
    "self.diagnostic_sink": "仅评测时记录拒绝草稿和细分原因；日常接口没有这个回调",
    "DetectorFactory": "构造本地语言识别器工厂，资料随安装包提供",
    "factory.load_profile": "读取本地字符统计特征，不调用外部模型",
    "factory.set_seed": "固定语言识别随机种子，便于复现判断",
    "detector.get_probabilities": "取得正文语言及置信度，不使用引用原文作为回答语言",
    "language_factory().create": "为当前检查建立独立识别器，隔离请求状态",
    "hasattr": "检查异常是否提供结构化校验细节",
    "exc.errors": "取得校验位置和错误类型；报告不保存异常中的密钥或配置对象",
    "slots.acquire": "非阻塞申请一个问答执行名额；名额满时接口立即返回繁忙",
    "slots.release": "归还问答名额；成功或异常都在 finally 中执行",
    "BoundedSemaphore": "创建有最大数量的进程内执行名额，防止无限并发占用模型资源",
    "super": "取得父类接口，用于初始化标准异常对象",
    "super().__init__": "初始化父类 RuntimeError，保存稳定错误码",
    "partition": "按分隔符拆成前缀、分隔符和后缀，用于 provider/model 配置",
    "dotenv_values": "读取指定配置文件为映射，不更改进程环境，也不输出密钥",
    "model_copy": "复制配置对象并替换指定字段，避免修改共享配置",
    "src.backup": "SQLite 在线一致性备份，包含已提交的 WAL 数据",
    "np.percentile": "按实测样本计算 P50/P95；小样本百分位不代表线上 SLA",
    "setdefault": "如果映射中没有当前分类，就创建其累计统计项",
    "Path": "构造文件路径对象，用于定位项目内源码、数据和报告",
    "TemporaryDirectory": "创建隔离临时目录，退出上下文时清理其文件",
    "update": "批量更新当前请求记录或独立配置副本中的字段",
    "SystemExit": "让验证脚本用非零退出码报告真实失败",
    "socket.socket": "创建本机端口探测 socket，使用后及时关闭",
    "sock.bind": "绑定 127.0.0.1 的临时端口，取得可用测试地址",
    "sock.getsockname": "读取操作系统为测试分配的端口",
    "process.kill": "仅强制停止当前脚本创建且无法正常退出的子进程",
    "process.poll": "检查隔离服务是否已经退出，发现启动失败",
    "process.terminate": "请求当前脚本创建的子进程正常停止",
    "process.wait": "等待自己创建的进程退出，设置超时避免无限阻塞",
    "entered.wait": "测试等待首请求进入执行阶段；有两秒超时保护",
    "release.wait": "故障测试中等待释放信号；超时会使测试失败",
    "subprocess.Popen": "启动隔离 HTTP 服务；密钥只通过进程环境传入",
    "subprocess.run": "按参数数组运行容器命令，不拼接 shell 命令字符串",
    "time.monotonic": "读取不受系统时钟校准影响的时间，用于启动截止时间",
    "time.sleep": "短暂等待健康轮询或在测试上游中模拟响应超时",
    "Thread": "构造测试服务或并发请求的后台线程",
    "Event": "创建测试线程之间的开始和释放信号",
    "ThreadingHTTPServer": "创建仅本机可访问的可控 HTTP 上游，模拟错误和恢复",
    "self.end_headers": "完成测试 HTTP 响应头",
    "self.rfile.read": "读取真实 SDK 发来的测试 HTTP 请求体",
    "self.send_header": "写入测试响应的内容类型和长度",
    "self.send_response": "设置测试上游的 HTTP 状态码",
    "self.wfile.write": "发送测试响应体；已超时的连接断开属于预期情况",
    "server.server_close": "关闭故障实验的本机监听 socket",
    "server.shutdown": "停止本机测试上游的请求循环",
    "thread.start": "启动当前实验的后台线程",
    "is_dir": "检查模型缓存目录是否存在",
    "remove": "从本脚本拥有的容器清理清单中移除已删除项",
    "os.chmod": "把临时令牌配置文件设置为仅当前用户可读写",
    "secrets.token_hex": "生成容器和卷的随机后缀，避免碰到已有资源",
    "secrets.token_urlsafe": "生成本次容器测试专用高强度令牌，不写入报告",
    "shutil.which": "检查容器命令是否存在，缺少时明确报告无法验证",
    "raise_for_status": "检查实际 HTTP 操作是否成功，失败立即停止后续成功断言",
    "httpx.ConnectError": "故障注入中模拟连接失败，不读取真实密钥",
    "httpx.ReadTimeout": "故障注入中模拟读取超时，验证分类回包和零自动重试",
    "len": "统计字符数或条目数；这里不是 Token 计数器",
    "bool": "把标题匹配结果转换为真或假",
    "chr": "按字符编码取得代码围栏标记",
    "reversed": "从尾部读取完整行以构造重叠段",
    "type": "取得异常类型以记录失败，不输出可能敏感的异常内容",
    "RuntimeError": "模拟或表示运行阶段的组件故障",
    "field_validator": "声明 Pydantic 自定义字段校验器",
    "np.any": "检查是否存在无效向量条目",
    "all": "检查所有项目或向量值都满足条件",
    "any": "检查是否存在匹配值或非零向量分量",
    "tobytes": "将 float32 向量序列化成 SQLite BLOB",
    "lower": "把文本统一成小写以分词匹配",
    "get_scores": "BM25 按查询词计算当前可见语料的相关分数",
    "passage_embed": "用固定版本语义模型计算文档片段向量",
    "query_embed": "用同一语义模型计算查询向量",
    "parametrize": "让同一个边界测试覆盖多个模式或错误输入",
    "range": "生成用于分段、重复实验或遍历的整数序列",
    "enumerate": "同时获得条目及位置编号",
    "zip": "逐项配对数据；strict=True 会拒绝两侧长度不一致",
    "sorted": "按照指定分数排序并保持可重复的顺序",
    "sum": "累计命中数或费用",
    "list": "把迭代结果收集为列表",
    "dict": "构造映射或把 SQLite Row 转为字典",
    "set": "去重，例如被实际使用的引用编号",
    "next": "从迭代器获取首个结果或指定默认值",
    "iter": "取得迭代器，便于读取模型向量",
    "int": "转换整数编号、维度或端口",
    "float": "把 NumPy 分数转换为可序列化数值",
    "str": "转换路径或错误信息为字符串",
    "max": "选择较大值，保护归一化分母或候选数量",
    "min": "限制返回数量",
    "isinstance": "检查配置对象类型",
    "print": "输出本次脚本运行进度，不输出密钥",
    "ValueError": "表示输入或数据不符合约束",
    "PermissionError": "表示可信身份没有写入权限",
    "HTTPException": "让 HTTP 层返回指定错误状态码",
    "json.loads": "把 JSON 文本解析为结构化对象",
    "json.dumps": "把对象序列化为 JSON",
    "hashlib.sha256": "生成内容、数据集或版本摘要，用于跳过重复计算及追溯",
    "hashlib.sha1": "核对 Git Blob 的内容标识，不用于密码加密",
    "base64.b64decode": "还原 GitHub Contents API 返回的原文字节",
    "urlparse": "拆解来源 URL 并限制允许的协议",
    "secrets.compare_digest": "以恒定时间方式比较服务端令牌",
    "sqlite3.connect": "建立一次数据库连接",
    "con.execute": "执行带参数的 SQL 查询或单条更新",
    "con.executescript": "创建表、外键与索引",
    "con.executemany": "在同一事务内批量写入片段和向量",
    "con.commit": "提交完整事务",
    "con.rollback": "异常时撤销未提交修改",
    "con.close": "关闭连接，释放资源",
    "np.array": "构造数值数组",
    "np.asarray": "把模型输出转换为统一 float32 数组",
    "np.empty": "创建空矩阵以表示没有可见片段",
    "np.stack": "把多条向量拼成检索矩阵",
    "np.isfinite": "拒绝 NaN 或无穷大的向量",
    "np.linalg.norm": "计算向量长度，用于 L2 归一化",
    "np.maximum": "限制除数下界，避免除零",
    "np.argsort": "按分数排序；stable 使同分结果固定",
    "np.frombuffer": "从 SQLite BLOB 还原 float32 向量",
    "math.log1p": "计算平滑正 IDF，使单篇可见文档也能被关键词命中",
    "Counter": "统计每个词出现在多少片段中",
    "replace": "复制不可变数据类并更新指定字段",
    "asdict": "把数据类及其嵌套字段转换为字典",
    "Lock": "保护模型首次初始化，避免并发重复加载",
    "TextEmbedding": "创建本地 FastEmbed 语义向量模型",
    "TextCrossEncoder": "创建本地查询与片段联合打分的重排模型",
    "BM25Okapi": "构建关键词检索索引；项目修正了 IDF 的小语料边界",
    "OpenAI": "创建兼容聊天 API 的客户端；并不代表默认使用 OpenAI 付费模型",
    "client.chat.completions.create": "发送带证据的结构化生成请求，读取服务商真实 usage",
    "Draft.model_validate_json": "校验模型返回 JSON 是否符合陈述及证据结构",
    "snapshot_download": "下载固定提交的公开模型文件，已有缓存时不联网",
    "perf_counter": "测量检索、重排、生成阶段的实际耗时",
    "mean": "对重复实验计算均值；重复运行不是新增独立样本",
    "ThreadPoolExecutor": "并行下载或执行并发边界测试",
    "httpx.get": "从官方固定版本接口读取公开文档",
    "response.raise_for_status": "拒绝失败的下载，不把错误页面当作资料",
    "FastAPI": "构造 HTTP 应用",
    "token_map": "读取服务端令牌与身份映射，正文不能指定权限",
    "HTMLResponse": "返回静态问答界面",
    "uvicorn.run": "在配置的地址启动 HTTP 服务",
    "ast.parse": "解析 Python 源码，不执行被分析代码",
    "ast.walk": "遍历语法树，发现函数、类和调用表达式",
    "ast.unparse": "把调用目标还原成可读名称",
    "ast.get_docstring": "读取源码里的职责解释",
}


def functions(path: Path) -> list[dict]:
    """ast.parse 解析模块；walk 查找函数、docstring 和其中全部调用（包含内部小函数）。"""
    tree = ast.parse(path.read_text())
    output = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = sorted({ast.unparse(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)})
            output.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "description": ast.get_docstring(node) or "待补充解释",
                    "calls": calls,
                }
            )
    return sorted(output, key=lambda f: f["line"])


def main() -> None:
    """functions 生成每个函数的职责及调用清单；使用源码解释与 GLOSSARY 解释被调用函数。"""
    paths = sorted(
        p
        for folder in ("app", "eval", "scripts", "tests")
        for p in (PROJECT_ROOT / folder).rglob("*.py")
    )
    modules = {p: functions(p) for p in paths}
    definitions = {}
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                definitions[node.name] = "构造对象：" + (ast.get_docstring(node) or node.name)
    for items in modules.values():
        for function in items:
            if function["name"] not in {"main", "__init__", "__len__", "_load"}:
                definitions[function["name"]] = function["description"]
    lines = [
        "# 函数功能与内部调用说明",
        "",
        "先读 pipeline → catalog → retrieval → generation，再看 HTTP 接口与评测。",
        "以下从源码生成。类的 dataclass / Pydantic 初始化函数由框架自动生成。",
        "函数内部调用包括内置函数和内部小函数；SQL 操作的职责也在源码注释中说明。",
        "",
    ]
    count = 0
    for path, items in modules.items():
        if not items:
            continue
        relative = path.relative_to(PROJECT_ROOT)
        lines.extend([f"## {relative}", ""])
        for function in items:
            count += 1
            lines.extend(
                [
                    f"### {function['name']}（第 {function['line']} 行）",
                    "",
                    function["description"],
                    "",
                    "内部使用：",
                    "",
                ]
            )
            for call in function["calls"]:
                tail = call.split(".")[-1]
                explanation = GLOSSARY.get(call) or GLOSSARY.get(tail) or definitions.get(tail)
                if tail == "_load":
                    explanation = next(
                        (f["description"] for f in items if f["name"] == "_load"),
                        "加载对应的本地模型",
                    )
                if not explanation:
                    explanation = {
                        "strip": "去掉首尾空白",
                        "split": "按分隔符切分字符串",
                        "splitlines": "按原始换行拆分文本",
                        "join": "连接字符串片段",
                        "encode": "编码字符串或计算模型向量，按所属对象区分",
                        "decode": "把原文字节解码为 UTF-8 文本",
                        "fetchone": "读取一个 SQL 查询结果",
                        "fetchall": "读取全部 SQL 查询结果",
                        "mkdir": "创建项目数据目录",
                        "read_text": "读取 UTF-8 文本",
                        "read_bytes": "读取原始字节用于摘要核验",
                        "write_text": "写入文档或评测报告",
                        "write_bytes": "保存未经改写的原文或许可证",
                        "hexdigest": "把摘要转换为十六进制标识",
                        "model_dump": "导出已经通过 Pydantic 验证的文档字段",
                        "get_secret_value": "只在必要调用时取得配置值，不输出密钥",
                        "append": "向列表增加一条记录",
                        "extend": "批量增加记录",
                        "insert": "在指定位置添加完整尾行",
                        "add": "添加去重条目或快照向量",
                        "get": "安全读取映射键或发送测试 GET 请求，依所属对象区分",
                        "post": "发送测试 POST 请求",
                        "delete": "删除文档或发测试 DELETE 请求",
                        "json": "解析接口返回的 JSON",
                        "map": "给线程池分配独立任务",
                        "search": "搜索匹配的引用标号",
                        "match": "从行首识别标题",
                        "fullmatch": "判断整个字符串是否为中文",
                        "findall": "提取全部关键词",
                        "sub": "去掉 Markdown 标题中的锚点注记",
                        "removesuffix": "去掉文件后缀",
                        "startswith": "检查协议、标题或围栏前缀",
                        "lstrip": "清理标题前缀",
                        "replace": "更换文档 ID 中的路径分隔符或模型缓存名称",
                        "items": "遍历映射键值",
                        "values": "遍历映射值",
                        "rglob": "列出源代码文件",
                        "is_file": "检查固定模型缓存是否完整",
                        "relative_to": "取得项目内的相对路径",
                        "now": "取得带时区的生成时间",
                        "isoformat": "生成可审计的时间字符串",
                        "parse_args": "解析命令行参数",
                        "add_argument": "声明命令行输入与范围",
                        "ArgumentParser": "构造脚本参数解析器",
                        "error": "拒绝错误的评测运行参数",
                        "platform": "记录测试机器环境",
                        "include_router": "注册 HTTP 路由",
                        "exception": "记录失败堆栈便于定位",
                        "getLogger": "构造模块日志器",
                        "approx": "按浮点容差比较预期分数",
                        "raises": "断言非法操作确实抛错",
                        "setattr": "注入测试替身，不调用付费接口",
                        "MockTransport": "模拟 HTTP 响应，保留真实 SDK 解析过程",
                        "Client": "构造 HTTP 客户端",
                        "Response": "构造测试响应",
                        "TestClient": "以内存 HTTP 请求验证真实 FastAPI 路由",
                        "SecretStr": "包装测试用密钥，使配置显示时脱敏",
                        "snapshot": "按可信身份读取可见片段快照",
                    }.get(tail, "构造对应对象或调用其方法；具体职责参见该对象的类说明和源码")
                lines.append(f"- `{call}()`：{explanation}")
            if not function["calls"]:
                lines.append("- 无额外函数调用。")
            lines.append("")
    lines.extend(
        [
            "## 前端函数",
            "",
            "- `api()`：fetch 携带访问令牌请求同源 API；json 解析结果；失败抛 Error。",
            "- `loadDocs()`：api 获取文档；createElement 建列表；textContent 安全显示标题。",
            "- `ask()`：api 发问答请求；createElement 构造引用；toFixed 格式化耗时。",
            "- `$()`：document.getElementById 按页面元素 ID 找到控件。",
            "",
            "## 新增官方资料示例中的函数",
            "",
            "这些文件是知识库资料，未作为业务模块执行；原文保持 MIT 官方版本。",
            "- 数据库示例 `get_db()`：调用 DBSession() 创建会话，yield 交给使用方，",
            "  在 finally 调用 db.close()。DBSession 由应用配置，示例没有定义它。",
            "- TestClient 示例 `read_main()`：返回固定问候数据，无内部函数调用。",
            "- `test_read_main()`：client.get() 请求接口，response.json() 读取响应，",
            "  检查状态和内容。模块用 FastAPI() 创建应用、TestClient(app) 创建客户端。",
            "",
        ]
    )
    lines.extend([
        "## 人工复核页面函数（eval/review_ui.html）",
        "",
        "以下只操作人工输入和本地评分接口，完全不调用大模型。",
        "",
        "| 函数 | 当前功能与内部调用 |",
        "|---|---|",
        "| el | document.getElementById 按固定 ID 找控件，是简短箭头函数 |",
        "| api | fetch 请求同源接口，response.json 解析数据；Error 表示真实失败 |",
        "| node | document.createElement 建节点，textContent 安全显示原文，不执行原文 HTML |",
        "| text | el 找控件，用 textContent 设置显示文字 |",
        "| setMessage | text 显示真实保存结果，classList.toggle 设置错误样式 |",
        "| visibleCases | el 读取筛选，map 配对题目与位置，filter 按实际人工记录筛选 |",
        "| renderProgress | text 与 style 更新进度；只读取服务端人工统计，未审完不显示全量率 |",
        "| renderGrid | visibleCases 取得列表，node 创建按钮，"
        "classList 根据已保存人工结果着色；点击调用 go |",
        "| appendSource | node 展示出处，split/map/join 保留原文行号；仅为 HTTP(S) 网址创建链接 |",
        "| renderEvidence | find 配对陈述与引用，node 展示原文，"
        "appendSource 展开完整文档；同时显示实际上下文与原标注 |",
        "| renderFields | node 建五项选择，恢复之前的真实人工值；"
        "onchange 只标记未保存，没有自动评分 |",
        "| renderCase | text 设置本题信息，调用 renderEvidence、renderFields、"
        "renderGrid、renderProgress |",
        "| go | confirm 提醒未保存修改；renderCase 切题，window.scrollTo 回到顶部 |",
        "| adjacent | visibleCases 与 findIndex 找当前题的位置，go 切换当前筛选中的上一／下一题 |",
        "| collectScore | el 读取人工选择，some 检查失败项，Error 拒绝空白判断或缺少失败原因 |",
        "| saveScore | collectScore 校验输入，api 发手动保存请求；成功后 renderCase 刷新，"
        "findIndex 寻找待审题；setMessage 报告失败 |",
        "| load | api 读冻结材料，localStorage.getItem 恢复称呼，"
        "findIndex 选择待审题，renderCase 展示 |",
        "| tr | 读取绑定同一来源的中文辅助译文，不改变原始评测或评分 |",
        "| appendOriginal | node 与 createElement 创建可展开的英文原记录，供核对译文 |",
        "| translatedAnswer | tr 翻译显示陈述，Set 去重原有引用；map/join 组合阅读文本 |",
        "",
        "页面事件回调：保存按钮调用 saveScore；导航调用 adjacent；筛选调用 visibleCases/go；",
        "备注输入只设置 dirty。提交表单时 preventDefault 避免意外刷新；",
        "beforeunload 在未保存时提示。匿名回调没有任何自动选通过或调用模型的步骤。",
        "",
    ])
    output = PROJECT_ROOT / "docs/functions.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Explained {count} Python functions, 4 RAG frontend and 20 manual-review helpers.")


if __name__ == "__main__":
    main()
