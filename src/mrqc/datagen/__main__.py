"""datagen CLI：生成 / 对账。

    py -X utf8 -m mrqc.datagen --out data/samples --count 60 --seed 20261003
    py -X utf8 -m mrqc.datagen --out data/paired --paired --per-defect 3 --seed 20261004
    py -X utf8 -m mrqc.datagen --verify data/samples data/paired
"""

import argparse
import sys
from pathlib import Path

from . import generate_clean, generate_paired
from .inject import INJECTION_ORDER
from .verify import verify_dataset


def _cmd_generate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if args.paired:
        summary = generate_paired(out, per_defect=args.per_defect,
                                  clean_controls=args.clean_controls, seed=args.seed)
        print("配对集生成完成：%s" % out)
        print("  缺陷注入：%d 类 × %d 份（ID 表见 plan/04 §7）"
              % (len(summary["defect_records"]), args.per_defect))
        print("  干净对照：%d 份" % summary["clean_controls"])
        for did in INJECTION_ORDER:
            n = summary["defect_records"].get(did, 0)
            print("    %-10s %d 份" % (did, n))
    else:
        summary = generate_clean(out, count=args.count, seed=args.seed)
        print("干净集生成完成：%s" % out)
        print("  共 %d 份（seed=%d）" % (summary["count"], summary["seed"]))
        for tid, n in sorted(summary["per_disease"].items()):
            print("    %-12s %d 份" % (tid, n))
    print("位级复现校验：同 seed 重跑本命令，git status 应零变化。")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    rc = 0
    for target in args.verify:
        result = verify_dataset(Path(target))
        print("对账：%s" % result["dataset"])
        print("  记录 %d 份（干净对照 %d 份）" % (result["records"], result["clean"]))
        covered = ", ".join("%s×%d" % (k, v) for k, v in sorted(result["defect_counts"].items()))
        print("  缺陷覆盖：%s" % (covered or "（无 defects.json）"))
        if result["problems"]:
            rc = 1
            print("  [失败] %d 个问题：" % len(result["problems"]))
            for problem in result["problems"][:50]:
                print("    - %s" % problem)
            if len(result["problems"]) > 50:
                print("    ...（其余 %d 条省略）" % (len(result["problems"]) - 50))
        else:
            print("  [通过] 往返一致、证据子串、日期与天数、缺陷 ID 全部对账通过")
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mrqc.datagen",
        description="合成病历生成器：固定 seed 产出带真值样本（干净集/注入配对集）+ truth 对账",
    )
    parser.add_argument("--out", default="", help="输出数据集目录（如 data/samples）")
    parser.add_argument("--count", type=int, default=60, help="干净集份数（按 3 病种均分）")
    parser.add_argument("--seed", type=int, default=20261003, help="确定性随机种子")
    parser.add_argument("--paired", action="store_true", help="生成注入缺陷配对集（默认干净集）")
    parser.add_argument("--per-defect", type=int, default=3, help="每类缺陷注入份数（配对模式）")
    parser.add_argument("--clean-controls", type=int, default=12, help="配对模式干净对照份数")
    parser.add_argument("--verify", nargs="*", default=None, metavar="DIR",
                        help="对数据集目录做 truth 对账（不给 --out 时使用）")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verify is not None:
        return _cmd_verify(args)
    if not args.out:
        parser.print_help()
        return 2
    return _cmd_generate(args)


if __name__ == "__main__":
    sys.exit(main())
