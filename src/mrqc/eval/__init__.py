"""评测基准：解析 F1（M2）/ 端到端检出（M4）。指标口径见 parse_f1 模块 docstring。"""

from .parse_f1 import (Counts, compare_cards, evaluate_dataset, evaluate_record,
                       f1_from_counts, validate_evidence)

__all__ = ["Counts", "compare_cards", "evaluate_dataset", "evaluate_record",
           "f1_from_counts", "validate_evidence"]
