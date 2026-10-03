"""部件渲染：RecordSpec → 六部件文本 + truth 参数卡（参数卡形状真值）。

证据纪律：truth 里每条 Evidence.quote 都直接引用本模块渲染出的行原文，
保证"摘录是部件原文的逐字子串"。注入在渲染之前改 spec，文本与真值同源。

文本骨架按病种形态（内科/外科）组织在本模块；临床口径（诊断名、药品池、
检验池、术式池等）来自 data/templates/*.json——改临床口径改模板，改文档
结构改这里。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..models.card import (Diagnosis, Evidence, FieldValue, LabResult, MedicationOrder,
                           PatientInfo, RecordCard, Signature, Surgery, TimelineEvent)
from .spec import MedSpec, RecordSpec, _fmt_hm

__all__ = ["RenderedRecord", "PART_FILENAMES", "render_record"]

PART_FILENAMES = {
    "入院记录": "admission.txt",
    "病程记录": "course.txt",
    "手术记录": "surgery.txt",
    "出院记录": "discharge.txt",
    "医嘱单": "orders.txt",
    "检验检查报告": "labs.txt",
}


@dataclass
class RenderedRecord:
    """一次渲染产物：部件名 → 文本；truth 参数卡。"""

    parts: Dict[str, str] = field(default_factory=dict)
    card: RecordCard = field(default_factory=RecordCard)


def _fv(value, part: str, quote: str, unit: str = "") -> FieldValue:
    """带单条证据的字段包装（confidence 固定 1.0：规则优先解析的合成真值）。"""
    return FieldValue(value=value, unit=unit, confidence=1.0,
                      evidence=[Evidence(part=part, quote=quote)])


def _join(lines: List[str]) -> str:
    return "\n".join(lines) + "\n"


def _blood_text(surgery) -> str:
    """手术经过里的用血描述（干净记录与 C-BLOOD-01 注入记录同用）。"""
    if not surgery.blood_used:
        return "未输血"
    return "术中输注%s%s%s，输血过程顺利" % (surgery.blood_drug, surgery.blood_dose, surgery.blood_dose_unit)


# ---------------------------------------------------------------- 入院记录

def _render_admission(spec: RecordSpec, card: RecordCard) -> List[str]:
    p = "入院记录"
    name_line = "姓名：%s    性别：%s" % (spec.name, spec.gender)
    lines = [
        "入院记录",
        name_line,
        "年龄：%d岁    科室：%s" % (spec.age, spec.department),
        "床号：%d床    住院号：%s" % (spec.bed, spec.hospital_no),
        "入院时间：%s" % _fmt_hm(spec.admission),
        "记录时间：%s" % _fmt_hm(spec.record_time),
    ]
    card.patient.name = _fv(spec.name, p, "姓名：%s" % spec.name)
    card.patient.gender = _fv(spec.gender, p, "性别：%s" % spec.gender)
    card.patient.age = _fv(spec.age, p, "年龄：%d岁" % spec.age, unit="岁")
    card.patient.department = _fv(spec.department, p, "科室：%s" % spec.department)
    card.patient.bed = _fv(spec.bed, p, "床号：%d床" % spec.bed)
    card.patient.admission_date = _fv(_fmt_hm(spec.admission), p, "入院时间：%s" % _fmt_hm(spec.admission))
    card.timeline.append(TimelineEvent(
        event="入院", time=_fv(_fmt_hm(spec.admission), p, "入院时间：%s" % _fmt_hm(spec.admission)),
        source_part=p,
    ))
    card.timeline.append(TimelineEvent(
        event="入院记录完成", time=_fv(_fmt_hm(spec.record_time), p, "记录时间：%s" % _fmt_hm(spec.record_time)),
        source_part=p,
    ))
    if not spec.drop_complaint:  # F-REQ-01 注入时删主诉段
        lines.append("主诉：%s。" % spec.complaint)
    lines.extend([
        "现病史：%s" % spec.hpi,
        "既往史：%s" % spec.past_history,
        "体格检查：%s" % spec.pe,
        "辅助检查：%s" % spec.assist_exam,
        "入院诊断：%s" % spec.admission_dx,
        "诊疗计划：%s" % spec.plan_text,
        "记录者：%s（住院医师）" % spec.resident,
    ])
    card.diagnoses.append(Diagnosis(
        type="入院", name=_fv(spec.admission_dx, p, "入院诊断：%s" % spec.admission_dx),
        icd10=_fv(spec.template["icd10"], p, "入院诊断：%s" % spec.admission_dx),
    ))
    card.signatures.append(Signature(
        role="住院医师", name=_fv(spec.resident, p, "记录者：%s（住院医师）" % spec.resident),
        date=_fv(spec.record_time.strftime("%Y-%m-%d"), p, "记录时间：%s" % _fmt_hm(spec.record_time)),
    ))
    return lines


# ---------------------------------------------------------------- 病程记录

def _render_course(spec: RecordSpec, card: RecordCard) -> List[str]:
    p = "病程记录"
    tpl = spec.template
    sections: List[tuple] = []  # (time, lines)

    first_lines = [
        "首次病程记录",
        _fmt_hm(spec.first_course_time),
        _fill_first_course(spec),
        "初步诊断：%s" % spec.admission_dx,
        "诊断依据：%s" % tpl["diagnosis_basis"],
        "鉴别诊断：%s" % tpl["diff_diagnosis"],
        "诊疗计划：%s" % spec.plan_text,
    ]
    sections.append((spec.first_course_time, first_lines))
    card.timeline.append(TimelineEvent(
        event="首次病程记录",
        time=_fv(_fmt_hm(spec.first_course_time), p, "首次病程记录\n%s" % _fmt_hm(spec.first_course_time)),
        source_part=p,
    ))

    if spec.surgery:
        surg = spec.surgery
        dt = _fmt_hm(spec.preop_discussion_time)
        disc_lines = [
            "术前讨论",
            dt,
            "参加人员：%s（主治医师）、%s（住院医师）" % (spec.attending, spec.resident),
            ("讨论意见：患者%s，术前诊断%s明确，有手术指征，无明确手术禁忌证。"
             "拟施手术：%s；拟施术者：%s；拟施麻醉方式：%s。"
             "术中术后可能发生的风险已向患者及家属充分交代，签署手术知情同意书。")
            % (spec.complaint, surg.preop_dx, surg.planned_name, surg.surgeon, surg.anesthesia),
            "讨论结论：术前诊断明确，有手术指征，%s行%s。"
            % (spec.template["surgery"]["urgency_word"], surg.planned_name),
        ]
        sections.append((spec.preop_discussion_time, disc_lines))
        card.timeline.append(TimelineEvent(
            event="术前讨论",
            time=_fv(_fmt_hm(spec.preop_discussion_time), p, "术前讨论\n%s" % dt),
            source_part=p, detail=surg.planned_name,
        ))

        post_lines = [
            "术后首次病程记录",
            _fmt_hm(spec.postop_course_time),
            _fill_postop_course(spec),
        ]
        sections.append((spec.postop_course_time, post_lines))
        card.timeline.append(TimelineEvent(
            event="术后首次病程",
            time=_fv(_fmt_hm(spec.postop_course_time), p, "术后首次病程记录\n%s" % _fmt_hm(spec.postop_course_time)),
            source_part=p,
        ))

    if spec.critical_handling_time and not spec.drop_critical_course:  # C-LAB-01 注入时删处置段
        dt = _fmt_hm(spec.critical_handling_time)
        crit_lines = ["危急值处置记录", dt, spec.critical_handling_text]
        sections.append((spec.critical_handling_time, crit_lines))
        card.timeline.append(TimelineEvent(
            event="危急值处置",
            time=_fv(_fmt_hm(spec.critical_handling_time), p, "危急值处置记录\n%s" % dt),
            source_part=p,
        ))

    if spec.blood_approval_time:  # 干净用血记录才有（C-BLOOD-01 注入后无此段）
        dt = _fmt_hm(spec.blood_approval_time)
        surg = spec.surgery
        blood_lines = [
            "输血病程记录",
            dt,
            "患者术中出血较多，术中输注%s%s%s，已完善输血前检查、签署输血知情同意书，"
            "经%s（主治医师）审核批准，输血过程顺利，无输血不良反应。"
            % (surg.blood_drug, surg.blood_dose, surg.blood_dose_unit, spec.attending),
        ]
        sections.append((spec.blood_approval_time, blood_lines))
        card.timeline.append(TimelineEvent(
            event="用血审批",
            time=_fv(_fmt_hm(spec.blood_approval_time), p, "输血病程记录\n%s" % dt),
            source_part=p,
        ))

    sections.append((spec.daily_course_time, [
        "日常病程记录",
        _fmt_hm(spec.daily_course_time),
        spec.daily_course_text,
    ]))

    lines: List[str] = []
    for _, sec_lines in sorted(sections, key=lambda x: x[0]):
        lines.extend(sec_lines)
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _fill_first_course(spec: RecordSpec) -> str:
    return spec.template["first_course"]["features_tpl"].replace(
        "{gender}", spec.gender).replace("{age}", str(spec.age)).replace("{complaint}", spec.complaint)


def _fill_postop_course(spec: RecordSpec) -> str:
    surg = spec.surgery
    return spec.template["surgery"]["postop_course_tpl"].replace(
        "{anesthesia}", surg.anesthesia).replace("{op_name}", surg.performed_name) \
        .replace("{blood_ml}", surg.blood_ml).replace("{blood_text2}", _blood_text(surg))


# ---------------------------------------------------------------- 手术记录

def _render_surgery(spec: RecordSpec, card: RecordCard) -> List[str]:
    p = "手术记录"
    surg = spec.surgery
    start_line = "手术开始时间：%s" % _fmt_hm(surg.start)
    end_line = "手术结束时间：%s" % _fmt_hm(surg.end)
    name_line = "手术名称：%s" % surg.performed_name
    op_note = (spec.template["surgery"]["op_note_tpl"]
               .replace("{finding}", surg.op_finding)
               .replace("{blood_ml}", surg.blood_ml)
               .replace("{blood_text}", _blood_text(surg)))
    lines = [
        "手术记录",
        "术前诊断：%s" % surg.preop_dx,
        "术后诊断：%s" % surg.postop_dx,
        name_line,
        start_line,
        end_line,
        "麻醉方式：%s" % surg.anesthesia,
        "术者：%s" % surg.surgeon,
        "助手：%s、%s" % (surg.assistants[0], surg.assistants[1]),
        "手术经过：%s" % op_note,
        "切口愈合等级：%s" % surg.incision,
    ]
    card.diagnoses.append(Diagnosis(
        type="术前", name=_fv(surg.preop_dx, p, "术前诊断：%s" % surg.preop_dx),
        icd10=_fv(spec.template["icd10"], p, "术前诊断：%s" % surg.preop_dx),
    ))
    card.diagnoses.append(Diagnosis(
        type="术后", name=_fv(surg.postop_dx, p, "术后诊断：%s" % surg.postop_dx),
        icd10=_fv(spec.template["icd10"], p, "术后诊断：%s" % surg.postop_dx),
    ))
    card.surgeries.append(Surgery(
        name=_fv(surg.performed_name, p, name_line),
        start_time=_fv(_fmt_hm(surg.start), p, start_line),
        duration_min=_fv(surg.duration_min, p, end_line, unit="分钟"),
        surgeon=_fv(surg.surgeon, p, "术者：%s" % surg.surgeon),
        assistants=[
            _fv(surg.assistants[0], p, "助手：%s、%s" % (surg.assistants[0], surg.assistants[1])),
            _fv(surg.assistants[1], p, "助手：%s、%s" % (surg.assistants[0], surg.assistants[1])),
        ],
        anesthesia=_fv(surg.anesthesia, p, "麻醉方式：%s" % surg.anesthesia),
        incision_healing=_fv(surg.incision, p, "切口愈合等级：%s" % surg.incision),
    ))
    card.timeline.append(TimelineEvent(
        event="手术", time=_fv(_fmt_hm(surg.start), p, start_line), source_part=p,
    ))
    if not (spec.drop_signature == "operator"):  # F-SIGN-01 注入时删术者签名行
        sig_line = "术者签名：%s（术者）" % surg.operator_signed_name
        lines.append(sig_line)
        card.signatures.append(Signature(
            role="术者", name=_fv(surg.operator_signed_name, p, sig_line),
            date=_fv(surg.start.strftime("%Y-%m-%d"), p, start_line),
        ))
    return lines


# ---------------------------------------------------------------- 出院记录

def _render_discharge(spec: RecordSpec, card: RecordCard) -> List[str]:
    p = "出院记录"
    tpl = spec.template
    course_through = _build_course_through(spec)
    adm_line = "入院时间：%s" % _fmt_hm(spec.admission)
    dis_line = "出院时间：%s" % _fmt_hm(spec.discharge)
    days_line = "住院天数：%d天" % spec.hospital_days
    dx_line = "出院诊断：%s" % spec.discharge_dx
    lines = [
        "出院记录",
        "姓名：%s  性别：%s  年龄：%d岁  科室：%s  床号：%d床"
        % (spec.name, spec.gender, spec.age, spec.department, spec.bed),
        "住院号：%s" % spec.hospital_no,
        adm_line,
        dis_line,
        days_line,
        "入院诊断：%s" % spec.admission_dx,
        dx_line,
        "诊疗经过：%s" % course_through,
        "出院情况：患者一般情况可，生命体征平稳，无特殊不适。",
        "出院医嘱：%s" % spec.discharge_orders,
        "记录者：%s（住院医师）" % spec.resident,
    ]
    card.patient.discharge_date = _fv(_fmt_hm(spec.discharge), p, dis_line)
    card.patient.hospital_days = _fv(spec.hospital_days, p, days_line, unit="天")
    card.timeline.append(TimelineEvent(
        event="出院", time=_fv(_fmt_hm(spec.discharge), p, dis_line), source_part=p,
    ))
    card.diagnoses.append(Diagnosis(
        type="出院", name=_fv(spec.discharge_dx, p, dx_line),
        icd10=_fv(tpl["icd10"], p, dx_line),
    ))
    if not (spec.drop_signature == "attending"):  # F-SIGN-01 注入时删上级审签行
        sig_line = "上级审签：%s（主治医师）" % spec.attending
        lines.append(sig_line)
        card.signatures.append(Signature(
            role="主治医师", name=_fv(spec.attending, p, sig_line),
            date=_fv(spec.discharge.strftime("%Y-%m-%d"), p, dis_line),
        ))
    return lines


def _build_course_through(spec: RecordSpec) -> str:
    tpl = spec.template
    if spec.surgery:
        return (tpl["course_through_tpl"]
                .replace("{complaint}", spec.complaint)
                .replace("{op_dt}", _fmt_hm(spec.surgery.start))
                .replace("{anesthesia}", spec.surgery.anesthesia)
                .replace("{op_name}", spec.surgery.performed_name))
    return (tpl["course_through_tpl"]
            .replace("{complaint}", spec.complaint)
            .replace("{ab}", tpl["ab_display"])
            .replace("{days}", str(spec.hospital_days)))


# ---------------------------------------------------------------- 医嘱单

def _render_orders(spec: RecordSpec, card: RecordCard) -> List[str]:
    p = "医嘱单"
    lines = [
        "长期医嘱单",
        "开始日期时间        医嘱内容                                        医师签名    停止日期时间        医师签名",
    ]
    admit_start = _fmt_hm(spec.admission.replace(minute=0))
    routine_line = "%s  %s护理常规  %s" % (admit_start, spec.department, spec.resident)
    lines.append(routine_line)
    lines.append("%s  二级护理  %s" % (admit_start, spec.resident))
    if spec.surgery:
        lines.append("%s  禁食水  %s  %s  %s" % (
            admit_start, spec.resident,
            _fmt_hm(spec.surgery.start), spec.resident))
        lines.append("%s  流质饮食  %s" % (_fmt_hm(spec.postop_course_time), spec.resident))

    longterm_meds = [m for m in spec.meds if m.longterm]
    temp_meds = [m for m in spec.meds if not m.longterm]
    for m in longterm_meds:
        line = "%s  %s %s%s %s %s  %s  %s  %s" % (
            _fmt_hm(m.start), m.drug, m.dose, m.dose_unit, m.route, m.frequency,
            spec.resident, _fmt_hm(m.stop), spec.resident)
        lines.append(line)
        _card_med(card, m, p, line)

    lines.append("")
    lines.append("临时医嘱单")
    lines.append("开始日期时间        医嘱内容                                        医师签名")
    for m in temp_meds:
        line = "%s  %s %s%s %s %s  %s" % (
            _fmt_hm(m.start), m.drug, m.dose, m.dose_unit, m.route, m.frequency, spec.resident)
        lines.append(line)
        _card_med(card, m, p, line)
    return lines


def _card_med(card: RecordCard, m: MedSpec, part: str, line: str) -> None:
    """一条医嘱槽位 → 参数卡 MedicationOrder（真值与医嘱单行同源）。"""
    is_blood = m.is_blood
    card.medications.append(MedicationOrder(
        drug_name=_fv(m.drug, part, line),
        dose=_fv(m.dose, part, line, unit=m.dose_unit),
        dose_unit=_fv(m.dose_unit, part, line),
        route=_fv(m.route, part, line),
        frequency=_fv(m.frequency, part, line) if m.frequency else None,
        start_time=_fv(_fmt_hm(m.start), part, line),
        stop_time=_fv(_fmt_hm(m.stop), part, line) if m.stop else None,
        is_antibiotic=_fv(m.is_antibiotic, part, line),
        antibiotic_level=_fv(m.antibiotic_level, part, line) if m.antibiotic_level else None,
        purpose=_fv("术中用血", part, line) if is_blood else None,
    ))


# ---------------------------------------------------------------- 检验检查报告

def _render_labs(spec: RecordSpec, card: RecordCard) -> List[str]:
    p = "检验检查报告"
    lines = ["检验检查报告"]
    for report in spec.lab_reports:
        lines.append("【%s】" % report.category)
        rt_line = "报告时间：%s" % _fmt_hm(report.report_time)
        lines.append(rt_line)
        for item in report.items:
            if item.value_text is not None:
                item_line = "检查所见：%s" % item.value_text
                lines.append(item_line)
                card.labs.append(LabResult(
                    item_name=_fv(item.item, p, item_line),
                    value_text=_fv(item.value_text, p, item_line),
                    report_time=_fv(_fmt_hm(report.report_time), p, rt_line),
                ))
            else:
                crit_txt = "危急值，" if item.critical else ""
                item_line = "%s %s %s %s（%s参考范围 %s）" % (
                    item.item, item.value, item.unit, item.flag, crit_txt, item.ref)
                lines.append(item_line)
                card.labs.append(LabResult(
                    item_name=_fv(item.item, p, item_line),
                    value=_fv(item.value, p, item_line),
                    unit=_fv(item.unit, p, item_line),
                    abnormal_flag=_fv(item.flag, p, item_line),
                    is_critical=_fv(item.critical, p, item_line),
                    report_time=_fv(_fmt_hm(report.report_time), p, rt_line),
                ))
    return lines


# ---------------------------------------------------------------- 总装配

def render_record(spec: RecordSpec) -> RenderedRecord:
    """spec → 六部件文本 + truth 参数卡。"""
    out = RenderedRecord()
    card = out.card
    card.patient = PatientInfo()
    out.parts["入院记录"] = _join(_render_admission(spec, card))
    out.parts["病程记录"] = _join(_render_course(spec, card))
    if spec.surgery:
        out.parts["手术记录"] = _join(_render_surgery(spec, card))
    out.parts["出院记录"] = _join(_render_discharge(spec, card))
    out.parts["医嘱单"] = _join(_render_orders(spec, card))
    out.parts["检验检查报告"] = _join(_render_labs(spec, card))
    # 时间轴按时间升序（value 为 "YYYY-MM-DD HH:MM"，字典序即时间序）
    card.timeline.sort(key=lambda ev: (ev.time.value if ev.time else "", ev.event))
    return out
