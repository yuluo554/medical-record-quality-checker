"""缺陷注入器：对干净 RecordSpec 做确定性变异，产出配对评测集。

对照 plan/04 §7 缺陷类型→规则→注入 三方共用 ID 表（M1 注入 / M3 规则 / M4 基准
不得单方改名）。一行多 ID 的时限行（入院记录/首次病程/术后首次病程超时限）拆为
F-TIME-01/02/03 三个注入。

注入发生在渲染之前（改 spec），文本与真值同源：truth.json 描述注入后文档
实际写了什么（抽取真值），defects.json 描述期望检出的缺陷（评测真值）。

also_expect 约定：同一注入隐含的其余结论记入 also_expect（评测按"文档全部
非 pass 集合"对账）。当前仅 C-LAB-02（重度贫血危急值）隐含 C-LAB-01（危急值
无处置）；F-SIGN-01 删术者签名时 C-SURG-02 按 M3 约定对签名缺失情形跳过
（缺失由 F-SIGN-01 负责），不记 also_expect。
"""

from typing import Any, Dict, List, Optional

from .spec import MedSpec, RecordSpec, _fmt_hm, _snap
from .rng import DetRng

__all__ = ["INJECTIONS", "INJECTION_ORDER", "InjectionMeta", "apply_injection"]


class InjectionMeta:
    """注入元数据 + 变异函数。diseases 为病种轮换顺序（第 k 份用 (k-1)%len）。"""

    def __init__(self, defect_id: str, channel: str, check_type: str,
                 description: str, diseases: tuple, apply_fn, also_expect: tuple = ()):
        self.defect_id = defect_id
        self.channel = channel
        self.check_type = check_type
        self.description = description
        self.diseases = diseases
        self.apply_fn = apply_fn
        self.also_expect = also_expect


def _inj_f_req_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    spec.drop_complaint = True
    return {"removed_section": "主诉"}


def _inj_f_sign_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    # k 奇数 → 外科删术者签名、内科删上级审签；k 偶数 → 删上级审签
    if spec.surgery and k % 2 == 1:
        spec.drop_signature = "operator"
        return {"removed_line": "手术记录-术者签名"}
    spec.drop_signature = "attending"
    return {"removed_line": "出院记录-上级审签"}


def _inj_f_time_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    spec.record_time = _snap(spec.admission, rng.randint(26 * 60, 32 * 60), rng)
    return {"field": "入院记录-记录时间", "value": _fmt_hm(spec.record_time), "limit_hours": 24}


def _inj_f_time_02(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    spec.first_course_time = _snap(spec.admission, rng.randint(9 * 60, 14 * 60), rng)
    return {"field": "首次病程记录-完成时间", "value": _fmt_hm(spec.first_course_time), "limit_hours": 8}


def _inj_f_time_03(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    if spec.surgery is None:
        raise ValueError("F-TIME-03 只适用于手术病种")
    spec.postop_course_time = _snap(spec.surgery.end, rng.randint(9 * 60, 13 * 60), rng)
    return {"field": "术后首次病程记录-完成时间", "value": _fmt_hm(spec.postop_course_time),
            "limit_hours": "即时（待核对）"}


def _inj_c_diag_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    before = len(spec.meds)
    removed = [m.drug for m in spec.meds if m.is_antibiotic]
    spec.meds = [m for m in spec.meds if not m.is_antibiotic]
    return {"removed_antibiotics": removed, "meds_before": before, "meds_after": len(spec.meds)}


def _inj_c_surg_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    if spec.surgery is None:
        raise ValueError("C-SURG-01 只适用于手术病种")
    alt = tpl["surgery"]["alt_name"]
    spec.surgery.performed_name = alt  # 手术记录改名；术前讨论拟施术式保持原名
    return {"surgery_name_in_record": alt, "planned_name_in_discussion": spec.surgery.planned_name}


def _inj_c_surg_02(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    if spec.surgery is None:
        raise ValueError("C-SURG-02 只适用于手术病种")
    candidates = ["王芳", "刘洋", "陈静", "杨帆", "赵磊", "周敏"]
    signed = rng.choice([d for d in candidates if d != spec.surgery.surgeon])
    spec.surgery.operator_signed_name = signed  # 仅签名行改名，正文术者不变
    return {"surgeon_in_body": spec.surgery.surgeon, "surgeon_in_signature": signed}


def _inj_c_lab_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    """危急值无处置：基础记录危急值变体开/关都行——关的先补一个危急值检验值，
    然后一律删掉处置病程段。"""
    if not spec.critical_value:
        crit_category = tpl["critical_category"]
        crit_item = tpl["critical_item"]
        for entry in tpl["labs"]:
            if entry["category"] == crit_category:
                for item in entry["items"]:
                    if item["item"] == crit_item and item.get("critical_pool"):
                        spec.critical_value = rng.choice(item["critical_pool"])
                        crit_time = _snap(spec.admission, rng.randint(20 * 60, 32 * 60), rng)
                        for report in spec.lab_reports:
                            if report.category == crit_category:
                                report.report_time = crit_time
                                for li in report.items:
                                    if li.item == crit_item:
                                        li.value = spec.critical_value
                                        li.flag = "↓"
                                        li.critical = True
        spec.critical_handling_time = _snap(
            spec.admission, rng.randint(20 * 60, 32 * 60) + 30, rng)
        spec.critical_handling_text = tpl["critical_handling_tpl"].replace("{v}", spec.critical_value)
    spec.drop_critical_course = True
    return {"lab_item": tpl["critical_item"], "critical_value": spec.critical_value,
            "removed_section": "危急值处置记录"}


def _inj_c_lab_02(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    for report in spec.lab_reports:
        for item in report.items:
            if item.item == "血红蛋白":
                item.value = "48"
                item.flag = "↓"
                item.critical = True  # 48g/L 达危急值口径 → 隐含 C-LAB-01（无处置）
                return {"lab_item": "血红蛋白", "value": "48", "report_category": report.category}
    raise ValueError("模板缺少血红蛋白检验项")


def _inj_c_ord_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    for m in spec.meds:
        if m.longterm and m.is_antibiotic and m.stop is not None:
            m.stop = _snap(spec.discharge, rng.randint(24 * 60, 26 * 60), rng)
            return {"drug": m.drug, "stop_time": _fmt_hm(m.stop),
                    "discharge_time": _fmt_hm(spec.discharge)}
    raise ValueError("记录中没有可注入的长期抗菌药医嘱")


def _inj_c_anti_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    special = tpl["meds"]["special_antibiotic"]
    spec.meds.append(MedSpec(
        drug=special["drug"], dose=special["dose"], dose_unit=special["dose_unit"],
        route=special["route"], frequency=special["frequency"], longterm=True,
        is_antibiotic=True, antibiotic_level=special["level"],
        start=_snap(spec.admission, 24 * 60, rng), stop=_snap(spec.discharge, -120, rng),
    ))
    return {"drug": special["drug"], "antibiotic_level": special["level"],
            "approval_record": "无"}


def _inj_c_blood_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    """术中用血无审批：确保用血医嘱存在 + 抹掉用血审批病程段。"""
    if spec.surgery is None:
        raise ValueError("C-BLOOD-01 只适用于用血变体病种")
    blood = tpl["blood_product"]
    spec.surgery.blood_used = True
    spec.surgery.blood_approved = False
    spec.surgery.blood_drug = blood["drug"]
    spec.surgery.blood_dose = blood["dose"]
    spec.surgery.blood_dose_unit = blood["dose_unit"]
    spec.blood_approval_time = None
    if not any(m.is_blood for m in spec.meds):
        spec.meds.append(MedSpec(
            drug=blood["drug"], dose=blood["dose"], dose_unit=blood["dose_unit"],
            route=blood["route"], frequency=blood["frequency"], longterm=False,
            is_blood=True, start=spec.surgery.start,
        ))
    return {"drug": blood["drug"], "dose": "%s%s" % (blood["dose"], blood["dose_unit"]),
            "approval_record": "无"}


def _inj_c_time_01(spec: RecordSpec, tpl: Dict[str, Any], rng: DetRng, k: int) -> Dict[str, Any]:
    if spec.surgery is None:
        raise ValueError("C-TIME-01 只适用于手术病种")
    # 出院时间改到手术开始前 23 小时（仍晚于入院时间，保持单一天数口径）
    spec.discharge = _snap(spec.surgery.start, -23 * 60, rng)
    spec.hospital_days = (spec.discharge.date() - spec.admission.date()).days
    # 长期医嘱停止时间随出院时间收缩，避免引入表外不一致（C-ORD-01 不误伤）
    for m in spec.meds:
        if m.longterm and m.stop is not None:
            m.stop = _snap(spec.discharge, -120, rng)
    return {"discharge_time": _fmt_hm(spec.discharge),
            "surgery_time": _fmt_hm(spec.surgery.start)}


INJECTION_ORDER = (
    "F-REQ-01", "F-SIGN-01", "F-TIME-01", "F-TIME-02", "F-TIME-03",
    "C-DIAG-01", "C-SURG-01", "C-SURG-02", "C-LAB-01", "C-LAB-02",
    "C-ORD-01", "C-ANTI-01", "C-BLOOD-01", "C-TIME-01",
)

INJECTIONS: Dict[str, InjectionMeta] = {m.defect_id: m for m in (
    InjectionMeta("F-REQ-01", "formal", "required_field",
                  "缺主诉必填段（删除主诉行）", ("cap", "appendicitis", "gallstone"), _inj_f_req_01),
    InjectionMeta("F-SIGN-01", "formal", "signature_format",
                  "缺术者/上级签名（删除签名行）", ("cap", "appendicitis", "gallstone"), _inj_f_sign_01),
    InjectionMeta("F-TIME-01", "formal", "timeliness",
                  "入院记录完成超24小时（改记录时间）", ("cap", "appendicitis", "gallstone"), _inj_f_time_01),
    InjectionMeta("F-TIME-02", "formal", "timeliness",
                  "首次病程记录超8小时（改完成时间）", ("cap", "appendicitis", "gallstone"), _inj_f_time_02),
    InjectionMeta("F-TIME-03", "formal", "timeliness",
                  "术后首次病程记录超时限（改完成时间）", ("appendicitis", "gallstone", "appendicitis"),
                  _inj_f_time_03),
    InjectionMeta("C-DIAG-01", "integrity", "cross_consistency",
                  "出院诊断与用药不匹配（删除全部抗菌药医嘱）", ("cap", "cap", "cap"), _inj_c_diag_01),
    InjectionMeta("C-SURG-01", "integrity", "cross_consistency",
                  "手术记录与术前讨论术式不一致（改手术名称）", ("appendicitis", "gallstone", "appendicitis"),
                  _inj_c_surg_01),
    InjectionMeta("C-SURG-02", "integrity", "cross_consistency",
                  "手术记录术者与签名不一致（改术者签名姓名）", ("appendicitis", "gallstone", "appendicitis"),
                  _inj_c_surg_02),
    InjectionMeta("C-LAB-01", "integrity", "lab_logic",
                  "危急值无病程处置记录（删危急值处置段）", ("cap", "cap", "cap"), _inj_c_lab_01),
    InjectionMeta("C-LAB-02", "integrity", "lab_logic",
                  "重度贫血值无处置与诊断（改血红蛋白值）", ("cap", "appendicitis", "gallstone"),
                  _inj_c_lab_02, also_expect=("C-LAB-01",)),
    InjectionMeta("C-ORD-01", "integrity", "cross_consistency",
                  "医嘱停止时间晚于出院时间（改停止时间）", ("cap", "appendicitis", "gallstone"), _inj_c_ord_01),
    InjectionMeta("C-ANTI-01", "integrity", "medication_logic",
                  "特殊使用级抗菌药无审批记录（加特殊级抗菌药医嘱）",
                  ("cap", "appendicitis", "gallstone"), _inj_c_anti_01),
    InjectionMeta("C-BLOOD-01", "integrity", "medication_logic",
                  "术中用血无审核审批记录（加输血医嘱且无审批病程）", ("gallstone", "gallstone", "gallstone"),
                  _inj_c_blood_01),
    InjectionMeta("C-TIME-01", "integrity", "timeline_logic",
                  "出院时间早于手术时间（改出院时间）", ("appendicitis", "gallstone", "appendicitis"),
                  _inj_c_time_01),
)}


def apply_injection(defect_id: str, spec: RecordSpec, template: Dict[str, Any],
                    rng: DetRng, k: int) -> Optional[Dict[str, Any]]:
    """执行注入，返回 defects.json 的 params。未注册 ID 返回 None。"""
    meta = INJECTIONS.get(defect_id)
    if meta is None:
        return None
    return meta.apply_fn(spec, template, rng, k)
