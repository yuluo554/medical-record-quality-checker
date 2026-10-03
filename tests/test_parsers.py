"""解析器测试：六部件解析 ↔ truth 全量对账、告警机制、证据逐字子串约束。

回归口径（plan/04 §2）：解析器用生成器样例做回归——直接对仓内 data/samples（60 份
干净记录）与 data/paired（54 份注入后文档）全量验收：解析卡与 truth.json 在
文本可导出路径上必须完全相等（排除口径见 mrqc/eval/parse_f1.py docstring）。
"""

import json
import shutil
from pathlib import Path

import pytest

from mrqc.eval.parse_f1 import compare_cards, f1_from_counts, validate_evidence
from mrqc.models import RecordCard
from mrqc.parsers import PARSERS, load_part_texts, parse_record_dir, parse_texts

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = REPO_ROOT / "data" / "samples"
PAIRED = REPO_ROOT / "data" / "paired"

# 配对集中按注入约定应产生缺区块告警的缺陷 ID（其余注入不改结构，只改值/删条件段）
_EXPECTED_WARNING_DEFECTS = ("F-REQ-01", "F-SIGN-01")


def _record_dirs(root: Path):
    return sorted(d for d in root.iterdir() if d.is_dir())


def _parse_match_truth(d: Path) -> list:
    """解析并与 truth 全路径对比，返回非排除路径差异列表。"""
    truth = RecordCard.from_dict(json.loads((d / "truth.json").read_text(encoding="utf-8")))
    card = parse_record_dir(d)
    counts = compare_cards(truth, card)
    problems = ["FP %s" % p for p in counts.fp_paths] + ["FN %s" % p for p in counts.fn_paths]
    return problems


def test_all_parsers_registered():
    assert sorted(PARSERS) == sorted(["入院记录", "病程记录", "手术记录",
                                      "出院记录", "医嘱单", "检验检查报告"])


def test_samples_60_parse_equals_truth():
    """60 份干净记录：解析卡 == truth（文本可导出路径全等）。"""
    bad = {}
    for d in _record_dirs(SAMPLES):
        problems = _parse_match_truth(d)
        if problems:
            bad[d.name] = problems[:8]
    assert not bad, "解析与真值不一致：%s" % bad


def test_paired_54_parse_equals_truth():
    """54 份注入后文档（truth 为注入后真值）：解析卡 == truth。"""
    bad = {}
    for d in _record_dirs(PAIRED):
        problems = _parse_match_truth(d)
        if problems:
            bad[d.name] = problems[:8]
    assert not bad, "解析与真值不一致：%s" % bad


def test_clean_samples_have_no_parse_warnings():
    warned = {d.name: parse_record_dir(d).parse_warnings for d in _record_dirs(SAMPLES)}
    warned = {k: v for k, v in warned.items() if v}
    assert not warned, "干净记录不应有解析告警：%s" % warned


def test_cap_samples_no_surgery_misreport():
    """CAP（内科 5 部件）无手术记录部件属正常：不得产生任何手术相关告警。"""
    for d in _record_dirs(SAMPLES):
        if not d.name.startswith("cap_"):
            continue
        card = parse_record_dir(d)
        assert not any("手术" in w for w in card.parse_warnings), d.name
        assert "手术记录" not in load_part_texts(d)[0]


def test_evidence_quotes_verbatim_samples():
    """DoD：证据摘录逐字子串约束实测——解析卡与 truth 卡对部件原文全量校验。"""
    bad = {}
    for d in _record_dirs(SAMPLES):
        part_texts, _ = load_part_texts(d)
        truth = RecordCard.from_dict(json.loads((d / "truth.json").read_text(encoding="utf-8")))
        violations = validate_evidence(truth, part_texts) + \
            validate_evidence(parse_record_dir(d), part_texts)
        if violations:
            bad[d.name] = violations[:5]
    assert not bad, "证据摘录不是部件原文逐字子串：%s" % bad


def test_evidence_quotes_verbatim_paired():
    bad = {}
    for d in _record_dirs(PAIRED):
        part_texts, _ = load_part_texts(d)
        card = parse_record_dir(d)
        violations = validate_evidence(card, part_texts)
        if violations:
            bad[d.name] = violations[:5]
    assert not bad, "证据摘录不是部件原文逐字子串：%s" % bad


def test_injected_defect_warning_behavior():
    """告警机制：删段/删行注入（F-REQ-01/F-SIGN-01）→ 缺区块告警；其余注入不误报。"""
    for d in _record_dirs(PAIRED):
        if not d.name.startswith("defect_"):
            continue
        defect_id = d.name[len("defect_"):].rsplit("_", 1)[0]
        warnings = parse_record_dir(d).parse_warnings
        if defect_id in _EXPECTED_WARNING_DEFECTS:
            assert warnings, "%s 注入应触发缺区块告警" % defect_id
        else:
            structural = [w for w in warnings if "缺少区块" in w or "缺少条目" in w or "未识别" in w]
            assert not structural, "%s 不应触发结构性告警：%s" % (defect_id, structural)


def test_detect_part_unknown_file_warning(tmp_path):
    (tmp_path / "mystery.txt").write_text("天书一份", encoding="utf-8")
    part_texts, warnings = load_part_texts(tmp_path)
    assert part_texts == {}
    assert any("无法识别部件" in w for w in warnings)


def test_duplicate_part_warning(tmp_path, capsys):
    src = SAMPLES / "cap_001"
    for f in src.glob("*.txt"):
        shutil.copy(f, tmp_path / f.name)
    shutil.copy(src / "admission.txt", tmp_path / "admission_copy.txt")
    _, warnings = load_part_texts(tmp_path)
    assert any("部件重复" in w for w in warnings)


def test_missing_required_block_warning(tmp_path):
    """F-REQ-01 同款结构：删主诉行 → 告警含"主诉"，其余字段照常解析。"""
    for f in (SAMPLES / "cap_001").glob("*.txt"):
        shutil.copy(f, tmp_path / f.name)
    lines = (tmp_path / "admission.txt").read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.startswith("主诉：")]
    (tmp_path / "admission.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    card = parse_record_dir(tmp_path)
    assert any("主诉" in w for w in card.parse_warnings)
    assert card.patient.name is not None and card.patient.name.value == "唐立新"
    assert card.diagnoses[0].name.value == "社区获得性肺炎"


def test_orders_routine_lines_not_medications():
    card = parse_record_dir(SAMPLES / "cap_001")
    drugs = [m.drug_name.value for m in card.medications]
    assert drugs == ["左氧氟沙星注射液", "注射用头孢呋辛钠", "盐酸氨溴索注射液", "0.9%氯化钠注射液"]


def test_medication_derivation_from_drugs_dict():
    """抗菌标记/分级/血液制品 purpose 必须从 knowledge.drugs 派生（与真值同源）。"""
    card = parse_record_dir(SAMPLES / "cap_001")
    by_drug = {m.drug_name.value: m for m in card.medications}
    assert by_drug["左氧氟沙星注射液"].is_antibiotic.value is True
    assert by_drug["左氧氟沙星注射液"].antibiotic_level.value == "限制级"
    assert by_drug["盐酸氨溴索注射液"].is_antibiotic.value is False
    assert by_drug["盐酸氨溴索注射液"].antibiotic_level is None
    assert by_drug["0.9%氯化钠注射液"].frequency is None  # 溶剂类无频次


def test_surgery_blood_med_purpose():
    """用血变体（gallstone）：输血医嘱 purpose=术中用血、剂量单位 U。"""
    blood_record = None
    for d in _record_dirs(SAMPLES):
        if not d.name.startswith("gallstone_"):
            continue
        truth = RecordCard.from_dict(json.loads((d / "truth.json").read_text(encoding="utf-8")))
        if any(m.purpose is not None for m in truth.medications):
            blood_record = d
            break
    assert blood_record is not None, "样例集中应存在用血记录"
    card = parse_record_dir(blood_record)
    blood_meds = [m for m in card.medications if m.purpose is not None]
    assert blood_meds and blood_meds[0].purpose.value == "术中用血"
    assert blood_meds[0].dose_unit.value == "U"
    assert blood_meds[0].frequency.value == "术中一次"


def test_course_timeline_detail_planned_surgery():
    """术前讨论事件 detail = 拟施手术名（C-SURG-01 比对锚）。"""
    card = parse_record_dir(SAMPLES / "appendicitis_001")
    ev = [e for e in card.timeline if e.event == "术前讨论"]
    assert len(ev) == 1
    assert ev[0].detail == "腹腔镜阑尾切除术"


def test_timeline_sorted_by_time():
    card = parse_record_dir(SAMPLES / "appendicitis_001")
    times = [e.time.value for e in card.timeline]
    assert times == sorted(times)


def test_surgeon_signature_mismatch_parsed_independently():
    """C-SURG-02：术者签名姓名被改，正文术者与签名分别解析（互不覆盖）。"""
    record = None
    for d in _record_dirs(PAIRED):
        if d.name.startswith("defect_C-SURG-02_"):
            record = d
            break
    assert record is not None
    card = parse_record_dir(record)
    surgery = card.surgeries[0]
    sig = [s for s in card.signatures if s.role == "术者"][0]
    assert surgery.surgeon.value != sig.name.value  # 注入改名后两者必然不同
    truth = RecordCard.from_dict(json.loads((record / "truth.json").read_text(encoding="utf-8")))
    assert surgery.surgeon.value == truth.surgeries[0].surgeon.value
    assert sig.name.value == truth.signatures[1].name.value


def test_parse_texts_pure_function():
    part_texts, warnings = load_part_texts(SAMPLES / "cap_001")
    assert warnings == []
    card = parse_texts(part_texts)
    assert card.patient.name.value == "唐立新"
