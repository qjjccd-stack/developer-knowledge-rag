"""把原始评测记录转成中文阅读报告；评分来自明确标记的助手复核，人类评分独立保留。"""

import json
from collections import Counter

from app.config import PROJECT_ROOT


def read_report(name: str) -> dict:
    """read_text 读取已有实测报告；缺少文件时明确返回未运行，绝不补造测试结果。"""
    path = PROJECT_ROOT / "reports" / name
    return json.loads(path.read_text()) if path.is_file() else {"status": "not_run"}


def case_details(row: dict) -> str:
    """把问题、回答、助手意见和各条证据整理成可展开段落，人工可按原文逐项复核。"""
    review = row.get("assistant_review", {})
    lines = [
        f"<details><summary>{row['id']} · {row['status']} · {row['question']}</summary>",
        "",
        "**复核意见**：" + review.get("notes", "待复核"),
        "",
        "**实际回答**：",
        "",
        row.get("answer", "运行错误"),
        "",
        "**生成引用**：",
        "",
    ]
    for claim in row.get("claims", []):
        lines.append("- 陈述：" + claim["text"])
        for evidence in claim["evidence"]:
            source = next(c for c in row["citations"] if c["id"] == evidence["id"])
            lines.append(
                f"  - 资料：{source['source']}，第 {source['start_line']}–{source['end_line']} 行"
            )
            lines.append("\n" + "\n".join("> " + s for s in evidence["quote"].splitlines()) + "\n")
    if not row.get("claims"):
        lines.append("没有展示未通过校验的生成内容；拒答原因：" + row.get("reason", ""))
    lines.extend(
        [
            "",
            "人类评分尚未填写；请在原始 JSON 的 human_review 中记录独立判断。",
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    """读取问答、并发和容器报告，计算实际分母并生成中文总览及逐题证据索引。"""
    answers = read_report("answer-review.json")
    hard = read_report("hard-negative-review.json")
    local = read_report("stability.json")
    live = read_report("live-stability.json")
    container = read_report("container-validation.json")
    rows = answers.get("rows", [])
    groups = Counter(r["category"] for r in rows)
    successes = Counter(
        r["category"] for r in rows if r.get("assistant_review", {}).get("task_success")
    )
    lines = [
        "# 实测结果与失败案例",
        "",
        "这份报告只整理已经运行的记录。评测集由开发过程中整理，属于开发集，不是独立盲测。",
        "正确性与支持关系由 Codex 按证据逐题复核；这不是人类标注。human_review 保持待填。",
        "",
        "## 真实问答",
        "",
        "模型配置：deepseek-chat。主评测 50 题，额外 6 道相近领域无答案题。",
        "主评测的成功要求：完成预期行为、答案充分、引用支持陈述，并使用问题的语言。",
        "",
        "| 类别 | 成功 / 总数 |",
        "|---|---:|",
    ]
    labels = {
        "answerable": "正常问答",
        "unanswerable": "无答案",
        "false_premise": "错误前提",
        "access_boundary": "权限边界",
    }
    for category, count in groups.items():
        lines.append(f"| {labels.get(category, category)} | {successes[category]} / {count} |")
    passed = sum(successes.values())
    lines.extend(
        [
            "",
            f"主评测完整任务通过：**{passed}/{len(rows)}**。"
            "机械状态/权限检查和助手语义复核分别保存，不把引用字串存在当成正确性证明。",
            "",
            "### 需要修复的问题",
            "",
            "- Q004：未召回组成 origin 的定义段落，模型拒答。",
            "- Q005、Q028：检索有正确证据，但生成引用校验失败。后来增加细分诊断码，原失败未覆盖。",
            "- Q021：给出 yield 的大致作用，未完整说明关闭数据库资源的方法。",
            "- Q008、Q023、F004：答案内容与引用相符，但语言与英文问题不一致。",
            "",
            "Q001、Q020 虽未命中原始 gold 段落，却找到了等价资料；证据复核认为回答成立。",
            "这说明检索标注命中和最终问答成功需要分别判断。",
            "",
            "额外六题询问文档未给出的具体版本或性能数字，六题均拒答；全部调用了真实模型。",
            "它们比天气类无答案题更难，因为检索能找到相近主题的资料。",
            "",
            "## 运行稳定性",
            "",
            "下表是热服务端到端 HTTP 时间。仅为本机小样本，不代表生产 SLA。",
            "",
            "| 生成方式 | 并发 | 请求数 | 失败 | P50 | P95 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for label, report in (("本地资料摘录", local), ("真实大模型", live)):
        for concurrency, group in report.get("concurrency", {}).items():
            lines.append(
                f"| {label} | {concurrency} | {group['requests']} | {group['failures']} | "
                f"{group['p50_ms'] / 1000:.2f}s | {group['p95_ms'] / 1000:.2f}s |"
            )
    if "cold_first_query" in local:
        lines.extend(
            [
                "",
                f"已有权重缓存的新进程首个摘录请求："
                f"{local['cold_first_query']['elapsed_ms'] / 1000:.2f}s。"
                "不是首次下载模型或操作系统冷缓存的耗时。",
            ]
        )
    if "cold_first_live_query" in live:
        lines.append(
            f"真实模型新进程首个请求：{live['cold_first_live_query']['elapsed_ms'] / 1000:.2f}s。"
        )
    lines.extend(
        [
            "",
            "故障注入使用真实 HTTP 和真实 SDK，模型响应为可控替身：",
            "超时、429 限流、500 错误均返回分类 503；下一请求恢复成功。",
            "四次应用请求只产生四次上游请求，验证 SDK 没有自动重试。",
            "应用并发满额时立即返回 QUERY_CAPACITY；失败会释放名额。容量限制按服务进程计算。",
            "",
            "## 容器与持久化",
            "",
            f"实测状态：**{container.get('status', 'not_run')}**。",
        ]
    )
    for check, ok in container.get("checks", {}).items():
        lines.append(f"- {check}：{'通过' if ok else '失败'}")
    lines.extend(
        [
            "",
            "容器验证只表示本机 Linux 容器可运行，不等于已公网发布。",
            "代码和依赖在镜像内；数据库与模型缓存保存在外部持久卷。",
            "",
            "## 原始记录",
            "",
            "- reports/answer-review.json：50 题回答、使用证据、真实 Token、逐题助手复核。",
            "- reports/hard-negative-review.json：6 题相近领域拒答。",
            "- reports/stability.json：本地模型并发、冷启动、故障注入。",
            "- reports/live-stability.json：真实生成的 HTTP 并发。",
            "- reports/container-validation.json：容器重建与数据验证。",
            "",
            "## 逐题复核",
            "",
        ]
    )
    lines.extend(case_details(row) for row in rows + hard.get("rows", []))
    path = PROJECT_ROOT / "docs/validation-results.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print("Written validation overview and", len(rows) + len(hard.get("rows", [])), "case reviews.")


if __name__ == "__main__":
    main()
