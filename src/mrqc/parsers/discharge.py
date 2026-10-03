"""出院记录解析器：键值行 → 出院诊断 + 出院时间/住院天数 + 出院时间轴 + 主治审签。

对照 render._render_discharge 逐行适配（渲染格式权威）：
  姓名/性别/年龄/科室/床号行、住院号、入院时间行不入参数卡（真值只取入院记录侧）；
  记录者行不产生签名（真值只收上级审签）。上级审签行可缺失（F-SIGN-01 注入）。
"""

from ..models import Diagnosis, Evidence, FieldValue, RecordCard, Signature, TimelineEvent
from .base import BaseParser, DT_RE, PartType, kv

__all__ = ["DischargeParser"]

# 结构必备键（上级审签可被 F-SIGN-01 合法删除，单列）
_REQUIRED_KEYS = ("姓名", "入院时间", "出院时间", "住院天数",
                  "入院诊断", "出院诊断", "诊疗经过", "出院医嘱", "记录者")


def _fv(value, quote: str, part: str, unit: str = "") -> FieldValue:
    return FieldValue(value=value, unit=unit, confidence=1.0,
                      evidence=[Evidence(part=part, quote=quote)])


class DischargeParser(BaseParser):
    part = PartType.DISCHARGE

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        p = self.part
        found = set()
        discharge_dt = ""

        for ln in [l.rstrip() for l in text.splitlines()]:
            if ln.startswith("上级审签：") and ln.endswith("（主治医师）"):
                found.add("上级审签")
                name = ln[len("上级审签："):-len("（主治医师）")]
                card.signatures.append(Signature(
                    role="主治医师", name=_fv(name, ln, p),
                    date=_fv(discharge_dt[:10], "出院时间：" + discharge_dt, p) if discharge_dt else None))
                continue
            matched = None
            for key in _REQUIRED_KEYS:
                v = kv(ln, key)
                if v is not None:
                    matched = (key, v)
                    break
            if matched is None:
                continue
            key, v = matched
            found.add(key)
            if key == "出院时间" and DT_RE.fullmatch(v):
                discharge_dt = v
                card.patient.discharge_date = _fv(v, "出院时间：" + v, p)
                card.timeline.append(TimelineEvent(
                    event="出院", time=_fv(v, "出院时间：" + v, p), source_part=p))
            elif key == "住院天数":
                days = v[:v.index("天")] if "天" in v else ""
                if days.isdigit():
                    card.patient.hospital_days = _fv(int(days), "住院天数：%s天" % days, p, unit="天")
            elif key == "出院诊断":
                # icd10 为知识派生字段（部件文本不含 ICD 编码）：解析层置 None
                card.diagnoses.append(Diagnosis(type="出院", name=_fv(v, "出院诊断：" + v, p)))

        missing = [k for k in _REQUIRED_KEYS if k not in found]
        if "上级审签" not in found:
            card.parse_warnings.append("出院记录缺少区块：上级审签")
        for key in missing:
            card.parse_warnings.append("出院记录缺少区块：%s" % key)
        return card
