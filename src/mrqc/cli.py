"""mrqc 命令行入口。

子命令与里程碑对应（未实现项 fail-fast，退出码 2，打印实现去向）：
  demo       架构自检演示（M0 即可用）
  parse      病历部件目录 → 参数卡 JSON（M2 完整实现）
  check      参数卡 + 规则库 → 质控结论（M3 完整实现）
  run        端到端：parse → check → （--report 导出 docx）（M5）
  benchmark  内置评测基准（M2/M4）
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__

_ROADMAP = [
    ("M1 数据先行", "病种模板 + 合成生成器（真值/植入缺陷） + 规范原文入库"),
    ("M2 解析层", "六部件解析器 → 病历参数卡，解析 F1 基准"),
    ("M3 知识与规则", "三层知识库 + 双通道规则引擎（依据关联/门控）"),
    ("M4 LLM 兜底", "防幻觉兜底抽取/复核 + 基准达标（F1≥0.95、误报 0）"),
    ("M5 编排与交付", "CLI 端到端 + docx 报告 + Web 面板（0 外链）"),
    ("M6 发布", "脱敏审计 + 干净环境验证 + GitHub 发布"),
]


def _not_implemented(message: str) -> int:
    print("[未实现] %s" % message, file=sys.stderr)
    return 2


def _cmd_demo(args: argparse.Namespace) -> int:
    from .knowledge import knowledge_dir, knowledge_status
    from .llm import llm_available
    from .models import FieldValue, PatientInfo, RecordCard
    from .parsers import registered_parts
    from .pipeline import CTX_TIMINGS, Pipeline
    from .rules import RuleEngine

    card = RecordCard(
        patient=PatientInfo(
            name=FieldValue(value="模拟患者（合成）"),
            department=FieldValue(value="普通外科"),
        )
    )
    engine = RuleEngine.load(knowledge_dir() / "rules")  # M3 起从知识库加载

    def node_parse(ctx):
        ctx["card"] = card  # M2 起替换为真实解析

    def node_check(ctx):
        ctx["findings"] = engine.check(ctx["card"])

    pipe = Pipeline(name="demo").add_node("解析", node_parse).add_node("质控", node_check)
    ctx = pipe.run()
    if not pipe.success:
        print("[错误] 流水线失败：%s" % [r.error for r in pipe.results if not r.ok])
        return 1

    findings = ctx.get("findings", [])
    print("mrqc %s —— 出院病历内涵质控智能审核系统（骨架自检）" % __version__)
    print()
    print("架构状态：")
    print("  [ok] 病历参数卡 schema（统一中间表示，M0 契约）")
    print("  [ok] 规则引擎（type 分派 + only_if 门控；无依据规则拒绝加载）")
    print("  [ok] 流水线编排（节点注册/耗时记录/失败即停）")
    print("  [ok] 解析器注册表：已注册 %d 个部件解析器（规则优先，证据逐字摘录）" % len(registered_parts()))
    ks = knowledge_status()
    print("  [ok] 知识库三层：raw=%d 份 / blocks=%d 块 / rules=%d 条（7 类 check_type 全注册）"
          % (ks["raw"], ks["blocks"], ks["rules"]))
    print("  [ok] LLM 兜底（低置信字段补抽 + 防幻觉回验）：%s"
          % ("已配置" if llm_available() else "未配置（自动走纯规则通路）"))
    print("  [--] 报告导出 / Web 面板：M5")
    print()
    print("演示运行：解析 → 质控（%d 条规则 → %d 条结论），流水线节点耗时："
          % (len(engine.rules), len(findings)))
    for name, seconds in ctx[CTX_TIMINGS].items():
        print("  %-4s %.4fs" % (name, seconds))
    print()
    print("路线图：")
    for m, desc in _ROADMAP:
        print("  %s  %s" % (m, desc))
    print()
    print("免责声明：本系统只做病历书写质量与记录一致性质控，不是临床决策支持工具；")
    print("演示数据全部为合成数据，不构成诊疗依据。")
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    from .parsers import parse_record_dir

    card = parse_record_dir(Path(args.input))
    print(json.dumps(card.to_dict(), ensure_ascii=False, indent=2))
    if card.parse_warnings:
        print("[提示] %d 条解析告警（详见 parse_warnings）" % len(card.parse_warnings), file=sys.stderr)
    return 0


def _run_llm_fallback(card, part_texts) -> None:
    """M4 LLM 兜底：低置信字段补抽。未配置静默走纯规则通路；失败降级不阻塞。"""
    from .llm import apply_fallback

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


def _cmd_check(args: argparse.Namespace) -> int:
    from .knowledge import knowledge_dir
    from .parsers import load_part_texts, parse_texts
    from .rules import RuleEngine

    part_texts, warnings = load_part_texts(Path(args.input))
    card = parse_texts(part_texts)
    card.parse_warnings[:0] = warnings  # 目录级告警排前（与 parse_record_dir 同口径）
    _run_llm_fallback(card, part_texts)  # M4：低置信字段补抽（未配置自动跳过）
    engine = RuleEngine.load(knowledge_dir() / "rules")
    findings = engine.check(card, part_texts=part_texts)
    print(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
    if not engine.rules:
        print("[提示] 规则库为空（M1/M3 填充 data/knowledge/rules/）", file=sys.stderr)
    non_pass = [f for f in findings if f.status != "pass"]
    print("[结论] 共 %d 条规则参评：%d 条结论非 pass（fail=%d / need_confirm=%d）"
          % (len(engine.rules), len(non_pass),
             sum(1 for f in non_pass if f.status == "fail"),
             sum(1 for f in non_pass if f.status == "need_confirm")),
          file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.report:
        return _not_implemented("--report docx 导出在 M5 实现（plan/05 里程碑 M5）")
    return _cmd_check(args)


def _cmd_benchmark(args: argparse.Namespace) -> int:
    bench = getattr(args, "bench", "")
    data_dir = Path(args.data) if args.data else None
    if bench == "parse":
        from .eval.parse_f1 import evaluate_dataset

        data_dir = data_dir or Path("data/samples")
        if not data_dir.is_dir():
            print("[错误] 数据集目录不存在：%s" % data_dir, file=sys.stderr)
            return 2
        r = evaluate_dataset(data_dir)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        if r["records_with_evidence_violations"]:
            return 1
        if r["f1"] < args.min_f1:
            print("[未达标] F1 %.4f < 门槛 %.4f" % (r["f1"], args.min_f1), file=sys.stderr)
            return 1
        return 0
    if bench == "detect":
        from .eval.detect import evaluate_dataset

        data_dir = data_dir or Path("data/paired")
        if not data_dir.is_dir():
            print("[错误] 数据集目录不存在：%s" % data_dir, file=sys.stderr)
            return 2
        r = evaluate_dataset(data_dir)
        print(json.dumps({k: v for k, v in r.items() if k != "details"},
                         ensure_ascii=False, indent=2))
        failed = (r["clean_false_positives"] > 0 or r["unexpected_findings"] > 0
                  or r["detection_rate"] < args.min_detection_rate)
        if failed:
            print("[未达标] 门槛：干净误报 0 + 非预期结论 0 + 检出率 ≥ %.2f" % args.min_detection_rate,
                  file=sys.stderr)
            return 1
        return 0
    return _not_implemented(
        "基准名可选 parse（解析 F1）/ detect（端到端检出，M4 已实现）；空名无默认基准"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mrqc",
        description="出院病历内涵质控智能审核系统（形式+内涵双通道质控，规则优先，LLM 兜底）",
    )
    parser.add_argument("--version", action="version", version="mrqc %s" % __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="架构自检演示（骨架即可用）")
    p_demo.set_defaults(fn=_cmd_demo)

    p_parse = sub.add_parser("parse", help="病历部件目录 → 病历参数卡 JSON")
    p_parse.add_argument("--input", required=True, help="病历部件集合目录（含 *.txt）")
    p_parse.set_defaults(fn=_cmd_parse)

    p_check = sub.add_parser("check", help="病历部件目录 → 质控结论 JSON")
    p_check.add_argument("--input", required=True, help="病历部件集合目录（含 *.txt）")
    p_check.set_defaults(fn=_cmd_check)

    p_run = sub.add_parser("run", help="端到端：解析 → 质控 → （可选 --report 导出 docx）")
    p_run.add_argument("--input", required=True, help="病历部件集合目录（含 *.txt）")
    p_run.add_argument("--report", default="", help="输出 docx 报告路径（M5）")
    p_run.set_defaults(fn=_cmd_run)

    p_bench = sub.add_parser("benchmark", help="内置评测基准（parse = 解析 F1；detect = 端到端检出）")
    p_bench.add_argument("bench", nargs="?", default="", choices=["", "parse", "detect"],
                         help="基准名；parse = 解析 F1（对 data/samples ↔ truth.json），"
                              "detect = 端到端检出（对 data/paired ↔ defects.json）")
    p_bench.add_argument("--data", default="", help="病历数据集目录（默认：parse→data/samples，detect→data/paired）")
    p_bench.add_argument("--min-f1", type=float, default=0.95, help="parse 基准 F1 门槛（默认 0.95，低于则退出码 1）")
    p_bench.add_argument("--min-detection-rate", type=float, default=0.95,
                         help="detect 基准主缺陷检出率门槛（默认 0.95，另含误报 0 硬门槛）")
    p_bench.set_defaults(fn=_cmd_benchmark)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except NotImplementedError as exc:
        return _not_implemented(str(exc))


if __name__ == "__main__":
    sys.exit(main())
