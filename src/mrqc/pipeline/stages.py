"""端到端流水线节点库（M5，plan/03 §6 数据流的节点化落地）。

节点：解析 → LLM 兜底（可选）→ 质控 → 汇总 → 导出。
节点工厂返回闭包供 Pipeline.add_node 注册；中间产物经 ctx 传递：
part_texts → card → findings → summary → 导出。
Web 面板（mrqc.web）复用同一套节点，保证 CLI 与 Web 结论同源。
"""

import sys
from collections import Counter
from pathlib import Path

from . import CTX_CARD, CTX_FINDINGS, CTX_PART_TEXTS, CTX_TIMINGS

__all__ = [
    "CTX_SUMMARY", "CTX_N_RULES", "STATUS_LABEL", "OVERALL_LABEL",
    "node_parse", "node_llm_fallback", "node_check", "node_summary", "node_export",
    "summarize", "build_pipeline", "run_llm_fallback",
]

CTX_SUMMARY = "summary"  # 分级统计 dict（summarize 产出）
CTX_N_RULES = "n_rules"  # 参评规则条数

# 结论状态 → 中文标签（与 eval.detect.STATUS_LABEL 同口径； report/web 共用本份）
STATUS_LABEL = {"pass": "通过", "fail": "不通过", "need_confirm": "待人工确认"}
OVERALL_LABEL = {"pass": "通过", "fail": "不通过", "need_confirm": "需人工复核"}


def summarize(findings, n_rules=None) -> dict:
    """结论清单 → 分级统计。

    口径与 eval.detect 一致：need_confirm 计入非 pass；分级分布只统计非 pass
    结论；依据关联率 = 挂 basis 的非 pass 结论占比（无非 pass 时记 1.0）。
    总体结论：有 fail → fail；否则有 need_confirm → need_confirm；否则 pass。
    """
    non_pass = [f for f in findings if f.status != "pass"]
    severity = Counter(f.severity.value for f in non_pass)
    if any(f.status == "fail" for f in findings):
        overall = "fail"
    elif non_pass:
        overall = "need_confirm"
    else:
        overall = "pass"
    n_basis = sum(1 for f in non_pass if f.basis is not None)
    return {
        "n_rules": n_rules,
        "n_findings": len(findings),
        "n_pass": len(findings) - len(non_pass),
        "n_fail": sum(1 for f in non_pass if f.status == "fail"),
        "n_need_confirm": sum(1 for f in non_pass if f.status == "need_confirm"),
        "non_pass_severity": {k: severity[k] for k in sorted(severity)},
        "basis_linkage_rate": round(n_basis / len(non_pass), 4) if non_pass else 1.0,
        "overall": overall,
        "overall_label": OVERALL_LABEL[overall],
    }


def run_llm_fallback(card, part_texts) -> None:
    """M4 LLM 兜底：低置信字段补抽。未配置静默走纯规则通路；失败降级不阻塞。"""
    from ..llm import apply_fallback

    try:
        stats = apply_fallback(card, part_texts)
    except Exception as exc:  # noqa: BLE001 —— 兜底层任何意外都不得阻塞质控主流程
        print("[LLM兜底] 意外失败已降级纯规则通路：%s" % exc, file=sys.stderr)
        return
    if not stats.get("available"):
        return  # 未配置：静默（demo 已展示配置状态）
    if stats.get("reason"):
        print("[LLM兜底] %s" % stats["reason"], file=sys.stderr)
        return
    if not stats.get("n_low_conf"):
        return  # 无低置信字段：无事可报
    print("[LLM兜底] 低置信字段 %d 个：应用 %d（丢弃：quote 非逐字 %d / 数值或时间非法 %d / 其他 %d）"
          % (stats["n_low_conf"], stats["n_applied"], stats["n_dropped_quote"],
             stats["n_dropped_range"], stats["n_dropped_other"]), file=sys.stderr)


def node_parse(input_dir) -> "callable":
    """节点1 解析：部件目录 → 部件文本 + 参数卡（目录缺失视为流水线失败）。"""
    input_dir = Path(input_dir)

    def fn(ctx):
        from ..parsers import load_part_texts, parse_texts

        if not input_dir.is_dir():
            raise FileNotFoundError("输入目录不存在：%s" % input_dir)
        part_texts, warnings = load_part_texts(input_dir)
        card = parse_texts(part_texts)
        card.parse_warnings[:0] = warnings  # 目录级告警排前（与 parse_record_dir 同口径）
        ctx[CTX_PART_TEXTS] = part_texts
        ctx[CTX_CARD] = card

    return fn


def node_llm_fallback() -> "callable":
    """节点2 LLM 兜底（可选）：低置信字段补抽，未配置/失败自动跳过。"""

    def fn(ctx):
        run_llm_fallback(ctx[CTX_CARD], ctx[CTX_PART_TEXTS])

    return fn


def node_check(rules_dir=None) -> "callable":
    """节点3 质控：加载规则库 → 双通道检查 → Findings。"""

    def fn(ctx):
        from ..knowledge import knowledge_dir
        from ..rules import RuleEngine

        engine = RuleEngine.load(Path(rules_dir) if rules_dir else knowledge_dir() / "rules")
        ctx[CTX_FINDINGS] = engine.check(ctx[CTX_CARD], part_texts=ctx.get(CTX_PART_TEXTS))
        ctx[CTX_N_RULES] = len(engine.rules)

    return fn


def node_summary() -> "callable":
    """节点4 汇总：分级统计 + 依据关联率 + 总体结论。"""

    def fn(ctx):
        ctx[CTX_SUMMARY] = summarize(ctx[CTX_FINDINGS], n_rules=ctx.get(CTX_N_RULES))

    return fn


def node_export(report_path="") -> "callable":
    """节点5 导出：--report 时参数卡+结论 → docx 报告（report extra，惰性导入）。"""
    out_path = Path(report_path) if report_path else None

    def fn(ctx):
        if out_path is None:
            return
        from ..report import export_report

        export_report(ctx[CTX_CARD], ctx[CTX_FINDINGS], out_path,
                      summary=ctx.get(CTX_SUMMARY))

    return fn


def build_pipeline(input_dir, report_path="", rules_dir=None, use_llm=True) -> "Pipeline":
    """按 plan/03 §6 组装五节点流水线（LLM 兜底节点常驻，未配置时内部静默跳过）。"""
    from . import Pipeline

    pipe = Pipeline(name="mrqc")
    pipe.add_node("解析", node_parse(input_dir))
    if use_llm:
        pipe.add_node("LLM兜底", node_llm_fallback())
    pipe.add_node("质控", node_check(rules_dir))
    pipe.add_node("汇总", node_summary())
    pipe.add_node("导出", node_export(report_path))
    return pipe
