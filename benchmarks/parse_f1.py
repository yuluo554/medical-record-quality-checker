#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""parse_f1 基准运行器（plan/04 §8）：解析参数卡 ↔ truth.json 字段路径级 P/R/F1。

用法（仓库根目录）：
    py -X utf8 benchmarks/parse_f1.py                      # data/samples 全量
    py -X utf8 benchmarks/parse_f1.py --data data/paired   # 配对集（注入后文档真值）
    py -X utf8 benchmarks/parse_f1.py --min-f1 0.95        # 门槛模式（M4 验收），exit 1 = 未达标

指标口径（知识派生路径排除、evidence 不入 F1 等）见 src/mrqc/eval/parse_f1.py
模块 docstring——口径改动须同步 plan/06 决策记录。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mrqc.eval.parse_f1 import evaluate_dataset  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="解析 F1 基准（字段路径级微平均）")
    parser.add_argument("--data", default="data/samples", help="病历数据集目录（默认 data/samples）")
    parser.add_argument("--min-f1", type=float, default=0.0, help="F1 门槛（低于则退出码 1）")
    args = parser.parse_args(argv)

    data_dir = Path(args.data)
    if not data_dir.is_dir():
        print("[错误] 数据集目录不存在：%s" % data_dir, file=sys.stderr)
        return 2
    r = evaluate_dataset(data_dir)
    print("parse_f1 基准：%s（%d 份病历）" % (r["dataset"], r["n_records"]))
    print("  路径级微平均：P=%.4f  R=%.4f  F1=%.4f （TP=%d FP=%d FN=%d）"
          % (r["precision"], r["recall"], r["f1"], r["tp"], r["fp"], r["fn"]))
    print("  含 parse_warnings 记录数：%d（注入缺陷记录的缺区块告警属正常）"
          % r["records_with_parse_warnings"])
    print("  证据逐字校验违规记录数：%d（须为 0）" % r["records_with_evidence_violations"])
    if r["fp_paths_sample"] or r["fn_paths_sample"]:
        print("  FP 样例：%s" % r["fp_paths_sample"][:10])
        print("  FN 样例：%s" % r["fn_paths_sample"][:10])
    if r["records_with_evidence_violations"]:
        return 1
    if r["f1"] < args.min_f1:
        print("[未达标] F1 %.4f < 门槛 %.4f" % (r["f1"], args.min_f1), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
