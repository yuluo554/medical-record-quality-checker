"""评测基准：解析 F1（M2）/ 配对集检出（M3，正式达标门槛 M4）。

指标口径见各模块 docstring（口径改动须同步 plan/06 决策表）。
"""

from .detect import detect_record, evaluate_dataset as evaluate_detect
from .parse_f1 import (Counts, compare_cards, evaluate_dataset, evaluate_record,
                       f1_from_counts, validate_evidence)

__all__ = ["Counts", "compare_cards", "evaluate_dataset", "evaluate_record",
           "f1_from_counts", "validate_evidence",
           "detect_record", "evaluate_detect"]
