"""医嘱单解析器：行式医嘱 → MedicationOrder（长期+临时合并）。

对照 render._render_orders 逐行适配（渲染格式权威）：
  行 = 起始时间␣␣内容␣␣医师签名[␣␣停止时间␣␣医师签名]；内容 = 药名 剂量+单位 途径 [频次]
  （频次可空——溶剂类临时医嘱）。护理常规/分级护理/禁食水/饮食类为非药品医嘱，静默跳过；
  未知内容行记 parse_warning。抗菌标记/分级/血液制品判定从 knowledge.drugs 派生
  （与生成器真值同源，不许另写第二套字典）。
"""

import re

from ..knowledge.drugs import classify_drug, is_blood_product
from ..models import Evidence, FieldValue, MedicationOrder, RecordCard
from .base import BaseParser, DT_RE, PartType

__all__ = ["OrderParser"]

_DOSE_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)(\S+)")
_SEG_SPLIT_RE = re.compile(r"\s{2,}")  # 列间隔 ≥2 空格（渲染用双空格，频次空缺时 3 空格）
_ROUTINE_RE = re.compile(r"护理|禁食|饮食")  # 非药品医嘱白名单（护理常规/二级护理/禁食水/流质饮食）


def _fv(value, quote: str, part: str) -> FieldValue:
    return FieldValue(value=value, confidence=1.0, evidence=[Evidence(part=part, quote=quote)])


def _parse_content(content: str):
    """内容段 → (drug, dose, dose_unit, route, freq)；非药品内容返回 None。

    内容 = 药名 剂量+单位 途径 [频次]，单空格分隔；剂量段 = 数字+单位粘合。
    """
    tokens = content.split(" ")
    if len(tokens) not in (3, 4):
        return None
    m = _DOSE_UNIT_RE.fullmatch(tokens[1])
    if not m or not m.group(2):
        return None
    return tokens[0], m.group(1), m.group(2), tokens[2], (tokens[3] if len(tokens) == 4 else "")


class OrderParser(BaseParser):
    part = PartType.ORDERS

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        p = self.part
        found = set()

        for ln in [l.rstrip() for l in text.splitlines()]:
            if ln.startswith("长期医嘱单"):
                found.add("长期医嘱单")
                continue
            if ln.startswith("临时医嘱单"):
                found.add("临时医嘱单")
                continue
            segs = _SEG_SPLIT_RE.split(ln)
            if not DT_RE.fullmatch(segs[0]):
                continue  # 表头等非医嘱行
            if len(segs) < 3:
                card.parse_warnings.append("医嘱单未识别行：%s" % ln)
                continue
            content = segs[1]
            parsed = _parse_content(content)
            if parsed is None:
                if _ROUTINE_RE.search(content):
                    continue  # 护理/禁食/饮食类非药品医嘱
                card.parse_warnings.append("医嘱单未识别行：%s" % ln)
                continue
            dose, dose_unit, route, freq = parsed[1:]
            drug = parsed[0]
            stop = segs[3] if len(segs) >= 5 and DT_RE.fullmatch(segs[3]) else None
            derived = classify_drug(drug)  # 抗菌标记/分级：与生成器真值共用 drugs.py
            card.medications.append(MedicationOrder(
                drug_name=_fv(drug, ln, p),
                dose=_fv(dose, ln, p),
                dose_unit=_fv(dose_unit, ln, p),
                route=_fv(route, ln, p),
                frequency=_fv(freq, ln, p) if freq else None,
                start_time=_fv(segs[0], ln, p),
                stop_time=_fv(stop, ln, p) if stop else None,
                is_antibiotic=_fv(derived["is_antibiotic"], ln, p),
                antibiotic_level=_fv(derived["antibiotic_level"], ln, p)
                if derived["antibiotic_level"] else None,
                purpose=_fv("术中用血", ln, p) if is_blood_product(drug) else None,
            ))

        for key in ("长期医嘱单", "临时医嘱单"):
            if key not in found:
                card.parse_warnings.append("医嘱单缺少区块：%s" % key)
        return card
