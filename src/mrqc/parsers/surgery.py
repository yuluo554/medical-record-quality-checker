"""手术记录解析器：键值行 → 术前/术后诊断 + Surgery + 手术时间轴 + 术者签名。

对照 render._render_surgery 逐行适配（渲染格式权威）。时长 = 结束-开始（分钟，
真值同口径）。术者签名行可缺失（F-SIGN-01 注入，C-SURG-02 可改签名姓名）：
缺失仅记 parse_warning，正文其余字段照常解析。
"""

from datetime import datetime

from ..models import Diagnosis, Evidence, FieldValue, RecordCard, Signature, Surgery, TimelineEvent
from .base import BaseParser, DT_RE, PartType, kv

__all__ = ["SurgeryParser"]

# 结构必备键（缺任一 → parse_warning，且不拼 Surgery 防半拉字段污染下游比对）
_REQUIRED_KEYS = ("术前诊断", "术后诊断", "手术名称", "手术开始时间", "手术结束时间",
                  "麻醉方式", "术者", "助手", "手术经过", "切口愈合等级")


def _fv(value, quote: str, part: str, unit: str = "") -> FieldValue:
    return FieldValue(value=value, unit=unit, confidence=1.0,
                      evidence=[Evidence(part=part, quote=quote)])


class SurgeryParser(BaseParser):
    part = PartType.SURGERY

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        p = self.part
        found = set()
        start_dt = end_dt = ""
        op_name = anesthesia = incision = surgeon = ""
        assistant_line = ""

        for ln in [l.rstrip() for l in text.splitlines()]:
            if ln.startswith("术者签名：") and ln.endswith("（术者）"):
                found.add("术者签名")
                name = ln[len("术者签名："):-len("（术者）")]
                card.signatures.append(Signature(
                    role="术者", name=_fv(name, ln, p),
                    date=_fv(start_dt[:10], "手术开始时间：" + start_dt, p) if start_dt else None))
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
            if key == "术前诊断":
                card.diagnoses.append(Diagnosis(type="术前", name=_fv(v, "术前诊断：" + v, p)))
            elif key == "术后诊断":
                card.diagnoses.append(Diagnosis(type="术后", name=_fv(v, "术后诊断：" + v, p)))
            elif key == "手术名称":
                op_name = v
            elif key == "手术开始时间" and DT_RE.fullmatch(v):
                start_dt = v
            elif key == "手术结束时间" and DT_RE.fullmatch(v):
                end_dt = v
            elif key == "麻醉方式":
                anesthesia = v
            elif key == "术者":
                surgeon = v
            elif key == "助手":
                assistant_line = ln
            elif key == "切口愈合等级":
                incision = v

        missing = [k for k in _REQUIRED_KEYS if k not in found]
        if "术者签名" not in found:
            card.parse_warnings.append("手术记录缺少区块：术者签名")
        for key in missing:
            card.parse_warnings.append("手术记录缺少区块：%s" % key)
        if missing or not start_dt or not end_dt:
            return card  # 结构不全（含时间行格式非法）：不拼 Surgery

        duration = int((datetime.strptime(end_dt, "%Y-%m-%d %H:%M")
                        - datetime.strptime(start_dt, "%Y-%m-%d %H:%M")).total_seconds() // 60)
        card.surgeries.append(Surgery(
            name=_fv(op_name, "手术名称：" + op_name, p),
            start_time=_fv(start_dt, "手术开始时间：" + start_dt, p),
            duration_min=_fv(duration, "手术结束时间：" + end_dt, p, unit="分钟"),
            surgeon=_fv(surgeon, "术者：" + surgeon, p),
            assistants=[_fv(a, assistant_line, p) for a in assistant_line[len("助手："):].split("、")],
            anesthesia=_fv(anesthesia, "麻醉方式：" + anesthesia, p),
            incision_healing=_fv(incision, "切口愈合等级：" + incision, p),
        ))
        card.timeline.append(TimelineEvent(
            event="手术", time=_fv(start_dt, "手术开始时间：" + start_dt, p), source_part=p))
        return card
