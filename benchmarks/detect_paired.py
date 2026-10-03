"""配对集端到端检出基准运行器（M3 首版出数；M4 在此扩正式门槛）。

指标实现与口径：src/mrqc/eval/detect.py（与 parse_f1 同分层：实现入库、
本文件只做 CLI 壳）。对账口径摘要：
- 缺陷记录主缺陷必须非 pass；also_expect 可选；期望外非 pass = 误报；
- 干净对照任何非 pass = 误报（M4 门槛 0，首版先行看数）。

运行：PYTHONDONTWRITEBYTECODE=1 py -X utf8 benchmarks/detect_paired.py \
        [--data data/paired] [--out 报告.md] [--min-detection-rate 0.95]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mrqc.eval.detect import evaluate_dataset, render_markdown  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="配对集端到端检出基准（M3 首版）")
    ap.add_argument("--data", default=str(ROOT / "data" / "paired"))
    ap.add_argument("--out", default="", help="追加写出 markdown 报告路径（可选）")
    ap.add_argument("--min-detection-rate", type=float, default=0.0,
                    help="门槛模式：主缺陷检出率低于该值退出码 1（M4 接管）")
    args = ap.parse_args(argv)

    data_dir = Path(args.data)
    if not data_dir.is_dir():
        print("[错误] 数据集目录不存在：%s" % data_dir, file=sys.stderr)
        return 2
    r = evaluate_dataset(data_dir)
    report = render_markdown(r)
    print(report)
    summary = {k: v for k, v in r.items() if k != "details"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print("[报告] 已写出 %s" % args.out, file=sys.stderr)
    failed = (r["clean_false_positives"] > 0
              or r["unexpected_findings"] > 0
              or r["detection_rate"] < args.min_detection_rate)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
