"""parse_f1 基准：解析参数卡 ↔ truth.json 字段路径级对账（plan/04 §2/§8）。

指标口径（M2 定稿，改动须同步 plan/06 决策记录）：
- 字段路径 = 参数卡区块叶子，如 medications[0].dose。FieldValue 节点按 .value
  对账；evidence 不入 F1（由 validate_evidence 对部件原文做全量逐字子串校验）；
  unit/confidence 不入 F1（dose 单位另有 dose_unit 路径）。
- 列表按下标对齐；单侧缺失按 FN（真值有）/ FP（解析多出）计。
- 双侧均为 None 的路径不计（无信息量）。
- 知识派生路径排除（文本中不存在编码/名称，由 M3 知识库派生补齐）：
    * diagnoses[*].icd10 —— ICD 编码不落部件文本；
    * labs[*].item_name 当该行 value_text 非空 —— 文本型检查行只落"检查所见"
      与报告类别，项目名不落文本（影像/心电图）。
- parse_warnings 是解析诊断信息不是抽取字段，不计 F1；干净集应为空（测试锁定）。
- 汇总为微平均（全记录路径级 TP/FP/FN 累加后算 P/R/F1）。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

from ..models import RecordCard
from ..parsers import load_part_texts, parse_record_dir

__all__ = ["Counts", "compare_cards", "f1_from_counts", "validate_evidence",
           "evaluate_record", "evaluate_dataset"]

CardLike = Union[RecordCard, Dict]

# 各列表区块参与对账的字段名（FieldValue 节点与普通字段统一走 _value_of）
_LIST_FIELDS = {
    "diagnoses": ["type", "name"],
    "surgeries": ["name", "start_time", "duration_min", "surgeon", "anesthesia",
                  "incision_healing", "assistants"],
    "medications": ["drug_name", "dose", "dose_unit", "route", "frequency",
                    "start_time", "stop_time", "is_antibiotic", "antibiotic_level", "purpose"],
    "labs": ["item_name", "value", "value_text", "unit", "abnormal_flag",
             "is_critical", "report_time"],
    "signatures": ["role", "name", "date"],
}
_TIMELINE_FIELDS = ["event", "time", "source_part", "detail"]
_PATIENT_KEYS = ("name", "gender", "age", "department", "bed",
                 "admission_date", "discharge_date", "hospital_days")


@dataclass
class Counts:
    """路径级对账计数（含误配路径明细，便于定位）。"""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    fp_paths: List[str] = field(default_factory=list)
    fn_paths: List[str] = field(default_factory=list)

    def add_tp(self) -> None:
        self.tp += 1

    def add_fp(self, path: str) -> None:
        self.fp += 1
        self.fp_paths.append(path)

    def add_fn(self, path: str) -> None:
        self.fn += 1
        self.fn_paths.append(path)

    def __iadd__(self, other: "Counts") -> "Counts":
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.fp_paths.extend(other.fp_paths)
        self.fn_paths.extend(other.fn_paths)
        return self


def _value_of(node: Optional[dict]):
    """FieldValue dict → .value；普通值原样；None → None。"""
    if node is None:
        return None
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node


def _compare_fv(truth_fv, parsed_fv, path: str, counts: Counts) -> None:
    if isinstance(truth_fv, list) or isinstance(parsed_fv, list):
        # FieldValue 列表（如 surgeries[*].assistants）：按下标对齐,逐元素按 .value 对账
        tl = truth_fv if isinstance(truth_fv, list) else []
        pl = parsed_fv if isinstance(parsed_fv, list) else []
        for j in range(max(len(tl), len(pl))):
            _compare_fv(tl[j] if j < len(tl) else None,
                        pl[j] if j < len(pl) else None, "%s[%d]" % (path, j), counts)
        return
    tv = _value_of(truth_fv)
    pv = _value_of(parsed_fv)
    if tv is None and pv is None:
        return  # 双侧缺失不计
    if tv == pv:
        counts.add_tp()
        return
    if tv is not None:
        counts.add_fn(path)
    if pv is not None:
        counts.add_fp(path)


def _compare_list(truth_list, parsed_list, base: str, fields, counts: Counts,
                  skip_field=None) -> None:
    """列表区块按下标对齐逐字段对账。skip_field(elem, name) 为 True 的路径不计
    （elem 为该侧元素，任一侧命中即排除——排除是字段级口径，与对齐无关）。"""
    n = max(len(truth_list), len(parsed_list))
    for i in range(n):
        t = truth_list[i] if i < len(truth_list) else None
        p = parsed_list[i] if i < len(parsed_list) else None
        for name in fields:
            path = "%s[%d].%s" % (base, i, name)
            if skip_field is not None:
                if t is not None and skip_field(t, name):
                    continue
                if p is not None and skip_field(p, name):
                    continue
            if t is None:
                if _value_of(p.get(name)) is not None:
                    counts.add_fp(path)
                continue
            if p is None:
                if _value_of(t.get(name)) is not None:
                    counts.add_fn(path)
                continue
            _compare_fv(t.get(name), p.get(name), path, counts)


def _labs_skip(elem, name: str) -> bool:
    """文本型检查行（value_text 非空）的 item_name 不计：项目名不落部件文本。"""
    return (name == "item_name" and isinstance(elem, dict)
            and _value_of(elem.get("value_text")) is not None)


def compare_cards(truth: CardLike, parsed: CardLike) -> Counts:
    """truth 参数卡 ↔ 解析参数卡 → 路径级计数。parse_warnings 不参与对账。"""
    t = truth.to_dict() if isinstance(truth, RecordCard) else truth
    p = parsed.to_dict() if isinstance(parsed, RecordCard) else parsed
    counts = Counts()

    for key in _PATIENT_KEYS:
        _compare_fv(t["patient"].get(key), p["patient"].get(key), "patient.%s" % key, counts)

    for section, fields in _LIST_FIELDS.items():
        skip = _labs_skip if section == "labs" else None
        _compare_list(t.get(section, []), p.get(section, []), section, fields, counts,
                      skip_field=skip)

    _compare_list(t.get("timeline", []), p.get("timeline", []),
                  "timeline", _TIMELINE_FIELDS, counts)
    return counts


def f1_from_counts(counts: Counts) -> Dict[str, float]:
    precision = counts.tp / (counts.tp + counts.fp) if (counts.tp + counts.fp) else 0.0
    recall = counts.tp / (counts.tp + counts.fn) if (counts.tp + counts.fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


# ---------------------------------------------------------------- 证据逐字校验

def validate_evidence(card: CardLike, part_texts: Dict[str, str]) -> List[str]:
    """参数卡全部 Evidence.quote 必须是所指部件原文的逐字子串（防幻觉纪律）。

    返回违规描述列表（空列表 = 全量通过）。part_texts = 部件名 → 原文。
    """
    d = card.to_dict() if isinstance(card, RecordCard) else card
    violations: List[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for ev in node.get("evidence", []) or []:
                part = ev.get("part", "")
                quote = ev.get("quote", "")
                text = part_texts.get(part)
                if text is None:
                    violations.append("%s: 证据部件不存在：%s" % (path, part))
                elif not quote or quote not in text:
                    violations.append("%s: 摘录非部件 %s 原文逐字子串：%r" % (path, part, quote[:50]))
            for k, v in node.items():
                walk(v, "%s.%s" % (path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    for section in ("patient", "diagnoses", "surgeries", "medications", "labs", "timeline", "signatures"):
        walk(d.get(section), section)
    return violations


# ---------------------------------------------------------------- 数据集评测

def evaluate_record(record_dir: Path) -> Dict:
    """单份病历：解析 + truth 对账 + 证据校验 → 指标明细。"""
    record_dir = Path(record_dir)
    truth = RecordCard.from_dict(json.loads((record_dir / "truth.json").read_text(encoding="utf-8")))
    card = parse_record_dir(record_dir)
    counts = compare_cards(truth, card)
    part_texts, _ = load_part_texts(record_dir)
    return {
        "record": record_dir.name,
        "counts": counts,
        "metrics": f1_from_counts(counts),
        "parse_warnings": list(card.parse_warnings),
        "evidence_violations": validate_evidence(card, part_texts),
    }


def evaluate_dataset(data_dir: Path) -> Dict:
    """数据集目录（每病历一子目录）→ 微平均指标 + 汇总诊断。"""
    data_dir = Path(data_dir)
    total = Counts()
    records = []
    n_warnings = 0
    n_evidence_bad = 0
    for d in sorted(x for x in data_dir.iterdir() if x.is_dir()):
        r = evaluate_record(d)
        total += r["counts"]
        if r["parse_warnings"]:
            n_warnings += 1
        if r["evidence_violations"]:
            n_evidence_bad += 1
        records.append(r)
    metrics = f1_from_counts(total)
    return {
        "dataset": str(data_dir),
        "n_records": len(records),
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "tp": total.tp,
        "fp": total.fp,
        "fn": total.fn,
        "fp_paths_sample": total.fp_paths[:20],
        "fn_paths_sample": total.fn_paths[:20],
        "records_with_parse_warnings": n_warnings,
        "records_with_evidence_violations": n_evidence_bad,
    }
