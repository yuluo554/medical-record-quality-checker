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
    from .knowledge import knowledge_status
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

    def node_parse(ctx):
        ctx["card"] = card  # M2 起替换为真实解析

    def node_check(ctx):
        engine = RuleEngine()  # M3 起从 data/knowledge/rules 加载
        ctx["findings"] = engine.check(ctx["card"])

    pipe = Pipeline(name="demo").add_node("解析", node_parse).add_node("质控", node_check)
    pipe.run()
    if not pipe.success:
        print("[错误] 流水线失败：%s" % [r.error for r in pipe.results if not r.ok])
        return 1

    print("mrqc %s —— 出院病历内涵质控智能审核系统（骨架自检）" % __version__)
    print()
    print("架构状态：")
    print("  [ok] 病历参数卡 schema（统一中间表示，M0 契约）")
    print("  [ok] 规则引擎骨架（type 分派 + only_if 门控；无依据规则拒绝加载）")
    print("  [ok] 流水线编排（节点注册/耗时记录/失败即停）")
    print("  [--] 解析器注册表：当前已注册 %d 个部件解析器（M2）" % len(registered_parts()))
    ks = knowledge_status()
    print("  [--] 知识库三层：raw=%d 份 / blocks=%d 块 / rules=%d 条（M1/M3）" % (ks["raw"], ks["blocks"], ks["rules"]))
    print("  [--] LLM 兜底：%s（M4；未配置时自动走纯规则通路）" % ("已配置" if llm_available() else "未配置"))
    print("  [--] 报告导出 / Web 面板：M5")
    print()
    print("演示运行：解析 → 质控（0 条规则 → 0 条结论），流水线节点耗时：")
    for name, seconds in pipe.run()[CTX_TIMINGS].items():
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


def _cmd_check(args: argparse.Namespace) -> int:
    from .knowledge import knowledge_dir
    from .parsers import parse_record_dir
    from .rules import RuleEngine

    card = parse_record_dir(Path(args.input))
    engine = RuleEngine.load(knowledge_dir() / "rules")
    findings = engine.check(card)
    print(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
    if not engine.rules:
        print("[提示] 规则库为空（M1/M3 填充 data/knowledge/rules/）", file=sys.stderr)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.report:
        return _not_implemented("--report docx 导出在 M5 实现（plan/05 里程碑 M5）")
    return _cmd_check(args)


def _cmd_benchmark(args: argparse.Namespace) -> int:
    return _not_implemented(
        "内置基准在 M2（解析 F1）/ M4（端到端检出）实现，脚本位于 benchmarks/"
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

    p_bench = sub.add_parser("benchmark", help="内置评测基准（解析 F1 / 端到端检出）")
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
