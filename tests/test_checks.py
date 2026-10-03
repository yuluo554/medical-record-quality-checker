"""七类 check_type 检查函数行为测试（手工构造参数卡，逐类型正反例）。"""

import json
from pathlib import Path

import pytest

from mrqc.knowledge import knowledge_dir
from mrqc.models import (Diagnosis, Evidence, FieldValue, LabResult, MedicationOrder,
                         PatientInfo, RecordCard, Signature, Surgery, TimelineEvent)
from mrqc.rules import RuleEngine, Severity

RULES_DIR = knowledge_dir() / "rules"


@pytest.fixture(scope="module")
def engine():
    return RuleEngine.load(RULES_DIR)


def _rule(eng, rid):
    hits = [r for r in eng.rules if r.id == rid]
    assert hits, "规则不存在：%s" % rid
    return hits[0]


def _run_one(eng, rid, card, texts=None):
    """只取指定规则的结论（引擎按规则库全量执行，此处按 rule_id 过滤）。"""
    return [f for f in eng.check(card, part_texts=texts or {}) if f.rule_id == rid]


def _fv(value, part="入院记录", quote="证据行"):
    return FieldValue(value=value, evidence=[Evidence(part=part, quote=quote)])


def _event(event, time, part="病程记录", detail=""):
    return TimelineEvent(event=event, time=_fv(time, part=part), source_part=part, detail=detail)


# ---------------------------------------------------------------- required_field

def test_required_field_fires_on_parse_warning(engine):
    rule = _rule(engine, "F-REQ-01")
    card = RecordCard(parse_warnings=["入院记录缺少区块：主诉"])
    texts = {"入院记录": "入院记录\n姓名：测试"}
    (f,) = _run_one(engine, rule.id, card, texts)
    assert f.status == "fail" and f.severity is Severity.HIGH
    assert f.evidence[0].part == "入院记录"
    assert "主诉" in f.suggestion


def test_required_field_silent_when_part_absent(engine):
    """部件整体缺失不判（部件可缺是既定口径，CAP 无手术记录）。"""
    rule = _rule(engine, "F-REQ-01")
    (f,) = _run_one(engine, rule.id, RecordCard(parse_warnings=["入院记录缺少区块：主诉"]), {})
    assert f.status == "pass"


def test_required_field_multi_block_lists_missing(engine):
    rule = _rule(engine, "R-REQ-05")
    card = RecordCard(parse_warnings=["出院记录缺少区块：出院医嘱"])
    texts = {"出院记录": "出院记录\n出院时间：2026-03-01 10:00"}
    (f,) = _run_one(engine, rule.id, card, texts)
    assert f.status == "fail"
    assert "出院医嘱" in f.suggestion


# ---------------------------------------------------------------- timeliness

def _timely_card(record_time="2026-03-01 09:00", admission="2026-03-01 08:00"):
    return RecordCard(
        patient=PatientInfo(admission_date=_fv(admission)),
        timeline=[_event("入院", admission, "入院记录"),
                  _event("入院记录完成", record_time, "入院记录")],
    )


def test_timeliness_pass_within_limit(engine):
    (f,) = _run_one(engine, "F-TIME-01", _timely_card())
    assert f.status == "pass"


def test_timeliness_fail_beyond_24h(engine):
    card = _timely_card(record_time="2026-03-02 10:00")  # 入院后 26 小时
    (f,) = _run_one(engine, "F-TIME-01", card)
    assert f.status == "fail"
    assert f.evidence  # 结论挂证据（入院时间 + 记录时间）


def test_timeliness_unverified_basis_yields_need_confirm(engine):
    """F-TIME-03 依据待核对 → 违例也只能 need_confirm（纪律，不硬判）。"""
    card = RecordCard(
        surgeries=[Surgery(start_time=_fv("2026-03-02 09:00", part="手术记录"),
                           duration_min=_fv(60, part="手术记录"))],
        timeline=[_event("手术", "2026-03-02 09:00", "手术记录"),
                  _event("术后首次病程", "2026-03-02 20:00")],  # 术毕 11 小时
    )
    texts = {"病程记录": "术后首次病程记录\n2026-03-02 20:00"}  # 满足门控关键词
    (f,) = _run_one(engine, "F-TIME-03", card, texts)
    assert f.status == "need_confirm"
    assert f.severity is Severity.NEED_CONFIRM
    assert f.basis.status == "待核对"


def test_timeliness_skips_when_event_missing(engine):
    (f,) = _run_one(engine, "F-TIME-02", RecordCard(patient=PatientInfo(admission_date=_fv("2026-03-01 08:00"))))
    assert f.status == "pass"


# ---------------------------------------------------------------- cross_consistency

def test_cross_surgery_name_mismatch(engine):
    card = RecordCard(
        surgeries=[Surgery(name=_fv("腹腔镜胆囊切除术", part="手术记录"))],
        timeline=[_event("术前讨论", "2026-03-01 09:00", detail="胆囊切除术")],
    )
    texts = {"病程记录": "术前讨论\n讨论意见：拟施手术：胆囊切除术。",
             "手术记录": "手术记录\n手术名称：腹腔镜胆囊切除术"}
    (f,) = _run_one(engine, "C-SURG-01", card, texts)
    assert f.status == "fail"
    assert "腹腔镜胆囊切除术" in f.suggestion


def test_cross_surgeon_signature_skip_when_signature_missing(engine):
    """注入跳过约定：术者签名缺失属 F-SIGN-01 范畴，C-SURG-02 不硬判。"""
    card = RecordCard(surgeries=[Surgery(surgeon=_fv("张伟", part="手术记录"))],
                      signatures=[])
    (f,) = _run_one(engine, "C-SURG-02", card, {"手术记录": "手术记录"})
    assert f.status == "pass"


def test_cross_surgeon_signature_mismatch(engine):
    card = RecordCard(
        surgeries=[Surgery(surgeon=_fv("张伟", part="手术记录"))],
        signatures=[Signature(role="术者", name=_fv("王芳", part="手术记录"))],
    )
    (f,) = _run_one(engine, "C-SURG-02", card, {"手术记录": "手术记录"})
    assert f.status == "fail"


def test_cross_med_stop_after_discharge(engine):
    card = RecordCard(
        patient=PatientInfo(discharge_date=_fv("2026-03-05 10:00", part="出院记录")),
        medications=[MedicationOrder(
            drug_name=_fv("注射用头孢呋辛钠", part="医嘱单"),
            stop_time=_fv("2026-03-06 10:00", part="医嘱单"))],
    )
    (f,) = _run_one(engine, "C-ORD-01", card)
    assert f.status == "fail"
    assert "注射用头孢呋辛钠" in f.suggestion


def test_cross_diagnosis_medication(engine):
    rule = _rule(engine, "C-DIAG-01")
    dx = Diagnosis(type="出院", name=_fv("社区获得性肺炎", part="出院记录"))
    no_ab = RecordCard(diagnoses=[dx])  # 全程无抗菌药
    (f,) = _run_one(engine, rule.id, no_ab)
    assert f.status == "fail"
    with_ab = RecordCard(diagnoses=[dx],
                         medications=[MedicationOrder(drug_name=_fv("注射用头孢呋辛钠", part="医嘱单"),
                                                      is_antibiotic=_fv(True, part="医嘱单"))])
    (f,) = _run_one(engine, rule.id, with_ab)
    assert f.status == "pass"
    other_dx = RecordCard(diagnoses=[Diagnosis(type="出院", name=_fv("急性阑尾炎", part="出院记录"))])
    (f,) = _run_one(engine, rule.id, other_dx)
    assert f.status == "pass"  # 非感染性诊断不触发


# ---------------------------------------------------------------- medication_logic

def test_medication_special_antibiotic_without_approval(engine):
    card = RecordCard(medications=[MedicationOrder(
        drug_name=_fv("注射用亚胺培南西司他丁钠", part="医嘱单"),
        antibiotic_level=_fv("特殊使用级", part="医嘱单"))])
    (f,) = _run_one(engine, "C-ANTI-01", card, {"病程记录": "首次病程记录\n2026-03-01 10:00"})
    assert f.status == "fail"
    assert f.severity is Severity.CRITICAL


def test_medication_special_antibiotic_with_approval_text(engine):
    card = RecordCard(medications=[MedicationOrder(
        drug_name=_fv("注射用亚胺培南西司他丁钠", part="医嘱单"),
        antibiotic_level=_fv("特殊使用级", part="医嘱单"))])
    (f,) = _run_one(engine, "C-ANTI-01", card, {"病程记录": "特殊使用级抗菌药经会诊同意后使用。"})
    assert f.status == "pass"


def test_medication_blood_without_approval_event(engine):
    card = RecordCard(medications=[MedicationOrder(
        drug_name=_fv("去白细胞悬浮红细胞", part="医嘱单"),
        purpose=_fv("术中用血", part="医嘱单"))])
    (f,) = _run_one(engine, "C-BLOOD-01", card)
    assert f.status == "fail"
    with_event = RecordCard(
        medications=card.medications,
        timeline=[_event("用血审批", "2026-03-01 12:00")])
    (f,) = _run_one(engine, "C-BLOOD-01", with_event)
    assert f.status == "pass"


# ---------------------------------------------------------------- lab_logic

def _lab(item, critical, value="2.5", unit="mmol/L"):
    return LabResult(item_name=_fv(item, part="检验检查报告"),
                     value=_fv(value, part="检验检查报告"),
                     unit=_fv(unit, part="检验检查报告"),
                     is_critical=_fv(critical, part="检验检查报告",
                                     quote="%s %s %s ↓（危急值，参考范围 3.5-5.3）" % (item, value, unit)))


def test_lab_critical_without_handling(engine):
    card = RecordCard(labs=[_lab("钾", True)])
    (f,) = _run_one(engine, "C-LAB-01", card, {"病程记录": "首次病程记录\n无危急值。"})
    assert f.status == "fail"
    assert "危急值" in f.suggestion
    handled = RecordCard(labs=[_lab("钾", True)])
    (f,) = _run_one(engine, "C-LAB-01", handled, {"病程记录": "危急值处置记录\n2026-03-01 11:00 复查。"})
    assert f.status == "pass"


def test_lab_critical_hemoglobin_unaddressed(engine):
    card = RecordCard(labs=[_lab("血红蛋白", True, value="48", unit="g/L")],
                      diagnoses=[Diagnosis(type="出院", name=_fv("社区获得性肺炎", part="出院记录"))])
    (f,) = _run_one(engine, "C-LAB-02", card, {"病程记录": "首次病程记录"})
    assert f.status == "fail"
    # 处置提及该项 → 通过
    (f,) = _run_one(engine, "C-LAB-02", card, {"病程记录": "复查血红蛋白较前上升。"})
    assert f.status == "pass"
    # 非危急值血红蛋白不触发
    normal = RecordCard(labs=[_lab("血红蛋白", False, value="131", unit="g/L")])
    (f,) = _run_one(engine, "C-LAB-02", normal, {"病程记录": ""})
    assert f.status == "pass"


# ---------------------------------------------------------------- signature_format

def test_signature_missing_attending_fails_only_with_discharge_part(engine):
    rule = _rule(engine, "F-SIGN-01")
    (f,) = _run_one(engine, rule.id, RecordCard(), {"出院记录": "出院记录\n出院时间：2026-03-05 10:00"})
    assert f.status == "fail"
    # 出院记录部件整体缺失 → 不判（部件可缺口径）
    (f,) = _run_one(engine, rule.id, RecordCard(), {})
    assert f.status == "pass"


def test_signature_missing_operator_when_surgery_present(engine):
    card = RecordCard(surgeries=[Surgery(surgeon=_fv("张伟", part="手术记录"))])
    (f,) = _run_one(engine, "F-SIGN-01", card, {"出院记录": "出院记录"})
    assert f.status == "fail"
    assert "术者" in f.suggestion


def test_signature_complete_passes(engine):
    card = RecordCard(
        surgeries=[Surgery(surgeon=_fv("张伟", part="手术记录"))],
        signatures=[Signature(role="术者", name=_fv("张伟", part="手术记录"), date=_fv("2026-03-01")),
                    Signature(role="主治医师", name=_fv("李四", part="出院记录"), date=_fv("2026-03-05")),
                    Signature(role="住院医师", name=_fv("王五", part="入院记录"), date=_fv("2026-03-01"))])
    findings = _run_one(engine, "F-SIGN-01", card, {"出院记录": "出院记录", "入院记录": "入院记录"})
    assert all(f.status == "pass" for f in findings)


# ---------------------------------------------------------------- timeline_logic

def test_timeline_discharge_before_surgery(engine):
    card = RecordCard(
        patient=PatientInfo(discharge_date=_fv("2026-03-01 10:00", part="出院记录")),
        surgeries=[Surgery(start_time=_fv("2026-03-02 09:00", part="手术记录"))],
    )
    (f,) = _run_one(engine, "C-TIME-01", card)
    assert f.status == "fail"
    assert f.severity is Severity.CRITICAL


def test_timeline_preop_after_surgery(engine):
    card = RecordCard(
        surgeries=[Surgery(start_time=_fv("2026-03-02 09:00", part="手术记录"))],
        timeline=[_event("术前讨论", "2026-03-02 10:00")],
    )
    (f,) = _run_one(engine, "R-TL-05", card, {"手术记录": "手术记录"})
    assert f.status == "fail"


def test_timeline_insufficient_data_passes(engine):
    """时间轴规则数据不足一律 pass（不硬判纪律）。"""
    texts = {"手术记录": "手术记录"}  # 满足手术类规则门控
    for rid in ("C-TIME-01", "R-TL-04", "R-TL-05", "R-TL-06", "R-TL-07", "R-TL-08"):
        (f,) = _run_one(engine, rid, RecordCard(), texts)
        assert f.status == "pass", rid


# ---------------------------------------------------------------- 门控与分派

def test_gate_scopes_surgical_rules(engine):
    """only_if 门控：CAP（无手术记录部件文本）不触发手术类规则。"""
    card = RecordCard(surgeries=[])  # 空卡
    texts = {"入院记录": "入院记录", "出院记录": "出院记录"}  # 无"手术记录"关键词
    findings = engine.check(card, part_texts=texts)
    fired = [f.rule_id for f in findings
             if f.rule_id in ("C-SURG-01", "C-SURG-02", "R-TL-04", "R-TL-05", "F-TIME-03")]
    assert fired == []


def test_all_seven_types_dispatched(engine):
    """全部 7 类 check_type 在真实规则库中均有注册 handler（无 NotImplementedError）。"""
    types = {r.type for r in engine.rules}
    from mrqc.rules import CHECK_TYPES
    assert types == set(CHECK_TYPES)
    texts = {"手术记录": "手术记录\n术后首次病程记录"}  # 覆盖全部门控关键词
    findings = engine.check(RecordCard(), part_texts=texts)
    assert len(findings) == len(engine.rules)
    assert all(f.status == "pass" for f in findings)
