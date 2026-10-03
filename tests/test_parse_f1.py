"""parse_f1 指标测试：路径级对账计数、知识派生路径排除、证据逐字校验。"""

import json
from pathlib import Path

from mrqc.eval.parse_f1 import (Counts, compare_cards, f1_from_counts,
                                validate_evidence)
from mrqc.models import (Diagnosis, Evidence, FieldValue, PatientInfo,
                         RecordCard, Surgery, TimelineEvent)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "data" / "samples"


def _fv(value):
    return FieldValue(value=value, evidence=[Evidence(part="入院记录", quote="q")])


def _mini_card(**overrides):
    card = RecordCard(
        patient=PatientInfo(name=_fv("张三"), age=FieldValue(value=54, unit="岁")),
        diagnoses=[Diagnosis(type="入院", name=_fv("社区获得性肺炎"), icd10=_fv("J18.9"))],
    )
    for k, v in overrides.items():
        setattr(card, k, v)
    return card


def test_perfect_match_full_tp():
    card = _mini_card()
    counts = compare_cards(card, card)
    assert counts.tp > 0 and counts.fp == 0 and counts.fn == 0


def test_value_mismatch_counts_fn_and_fp():
    truth = _mini_card()
    parsed = _mini_card()
    parsed.patient.name.value = "李四"
    counts = compare_cards(truth, parsed)
    assert counts.fn == 1 and counts.fp == 1
    assert counts.fn_paths == ["patient.name"] and counts.fp_paths == ["patient.name"]


def test_both_none_skipped_single_sided_missing_counts():
    truth = _mini_card()
    parsed = _mini_card()
    parsed.patient.age = None  # 单侧缺失 → FN
    counts = compare_cards(truth, parsed)
    assert counts.fn_paths == ["patient.age"]
    truth2 = _mini_card()
    parsed2 = _mini_card()
    truth2.patient.age = None  # 真值缺失、解析多出 → FP
    counts2 = compare_cards(truth2, parsed2)
    assert counts2.fp_paths == ["patient.age"]


def test_icd10_excluded_from_metric():
    """知识派生路径（icd10）不计入：真值有编码、解析为 None 也不算 FN。"""
    truth = _mini_card()
    parsed = _mini_card()
    parsed.diagnoses[0].icd10 = None
    counts = compare_cards(truth, parsed)
    assert counts.fn == 0 and counts.fp == 0


def test_labs_text_row_item_name_excluded():
    """文本型检查行（value_text 非空）的 item_name 不计入（项目名不落文本）。"""
    from mrqc.models import LabResult

    text_row_truth = LabResult(item_name=_fv("胸部CT"), value_text=_fv("片状影"))
    text_row_parsed = LabResult(item_name=_fv("影像"), value_text=_fv("片状影"))
    truth = _mini_card(labs=[text_row_truth])
    parsed = _mini_card(labs=[text_row_parsed])
    counts = compare_cards(truth, parsed)
    assert counts.fp == 0 and counts.fn == 0


def test_labs_numeric_row_item_name_counted():
    """数值行的 item_name 在文本中,正常计入。"""
    from mrqc.models import LabResult

    truth = _mini_card(labs=[LabResult(item_name=_fv("白细胞计数"), value=_fv("16.8"))])
    parsed = _mini_card(labs=[LabResult(item_name=_fv("白细胞计数"), value=_fv("17.0"))])
    counts = compare_cards(truth, parsed)
    assert counts.fn_paths == ["labs[0].value"] and counts.fp_paths == ["labs[0].value"]


def test_list_length_mismatch():
    truth = _mini_card(surgeries=[])
    parsed = _mini_card(surgeries=[Surgery(name=_fv("阑尾切除术"))])
    counts = compare_cards(truth, parsed)
    assert counts.fp > 0 and all(p.startswith("surgeries[0].") for p in counts.fp_paths)


def test_timeline_detail_compared():
    truth = _mini_card(timeline=[TimelineEvent(event="术前讨论", detail="术式A")])
    parsed = _mini_card(timeline=[TimelineEvent(event="术前讨论", detail="术式B")])
    counts = compare_cards(truth, parsed)
    assert counts.fp_paths == ["timeline[0].detail"] and counts.fn_paths == ["timeline[0].detail"]


def test_f1_from_counts():
    c = Counts(tp=8, fp=1, fn=1)
    m = f1_from_counts(c)
    assert abs(m["precision"] - 8 / 9) < 1e-9
    assert abs(m["recall"] - 8 / 9) < 1e-9
    assert abs(m["f1"] - 8 / 9) < 1e-9


def test_validate_evidence_flags_hallucinated_quote():
    card = RecordCard(patient=PatientInfo(name=FieldValue(
        value="张三", evidence=[Evidence(part="入院记录", quote="姓名：张三根本没这行")])))
    violations = validate_evidence(card, {"入院记录": "入院记录\n姓名：张三\n"})
    assert len(violations) == 1 and "逐字子串" in violations[0]


def test_validate_evidence_flags_missing_part():
    card = RecordCard(patient=PatientInfo(name=_fv("张三")))
    violations = validate_evidence(card, {"出院记录": "出院记录"})
    assert len(violations) == 1 and "部件不存在" in violations[0]


def test_benchmark_end_to_end_on_cap_001():
    """基准函数通路：cap_001 全对账 → F1 = 1.0（排除路径外零差异）。"""
    from mrqc.eval.parse_f1 import evaluate_record

    r = evaluate_record(SAMPLES / "cap_001")
    assert r["metrics"]["f1"] == 1.0
    assert r["parse_warnings"] == []
    assert r["evidence_violations"] == []
