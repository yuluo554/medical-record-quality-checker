"""入院记录解析器：行式键值 → PatientInfo + 入院诊断 + 时间轴 + 住院医师签名。

对照 render._render_admission 逐行适配（渲染格式权威）：
  姓名：X    性别：Y / 年龄：N岁    科室：D / 床号：B床    住院号：H
  入院时间：DT / 记录时间：DT / 主诉：… / 入院诊断：… / 记录者：X（住院医师）
证据摘录 = 键前缀 + 抽取值（部件行原文的逐字子串）。
"""

import re
from typing import Optional

from ..models import Diagnosis, Evidence, FieldValue, RecordCard, Signature, TimelineEvent
from .base import BaseParser, DT_RE, PartType, kv

__all__ = ["AdmissionParser"]

# 结构必备键（缺任一 → parse_warning；F-REQ-01 删主诉在此暴露，不抛异常）
_REQUIRED_KEYS = (
    "姓名", "性别", "年龄", "科室", "床号", "入院时间", "记录时间",
    "主诉", "现病史", "既往史", "体格检查", "辅助检查", "入院诊断", "诊疗计划", "记录者",
)

_NAME_GENDER_RE = re.compile(r"姓名：(\S+)\s+性别：(\S+)")
_AGE_DEPT_RE = re.compile(r"年龄：(\d+)岁\s+科室：(.+?)\s*$")
_BED_RE = re.compile(r"床号：(\d+)床")
_RESIDENT_RE = re.compile(r"记录者：(.+?)（住院医师）$")


def _fv(value, quote: str, part: str, unit: str = "") -> FieldValue:
    return FieldValue(value=value, unit=unit, confidence=1.0,
                      evidence=[Evidence(part=part, quote=quote)])


class AdmissionParser(BaseParser):
    part = PartType.ADMISSION

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        p = self.part
        lines = [ln.rstrip() for ln in text.splitlines()]
        found = set()
        record_time = ""  # 记录时间（签名日期来源，渲染恒在记录者行之前）

        for ln in lines:
            m = _NAME_GENDER_RE.search(ln)
            if m and kv(ln, "姓名") is not None:
                found.update(("姓名", "性别"))
                card.patient.name = _fv(m.group(1), "姓名：" + m.group(1), p)
                card.patient.gender = _fv(m.group(2), "性别：" + m.group(2), p)
                continue
            m = _AGE_DEPT_RE.search(ln)
            if m and kv(ln, "年龄") is not None:
                found.update(("年龄", "科室"))
                card.patient.age = _fv(int(m.group(1)), "年龄：%d岁" % int(m.group(1)), p, unit="岁")
                card.patient.department = _fv(m.group(2), "科室：" + m.group(2), p)
                continue
            m = _BED_RE.search(ln)
            if m and kv(ln, "床号") is not None:
                found.add("床号")
                card.patient.bed = _fv(int(m.group(1)), "床号：%d床" % int(m.group(1)), p)
                continue
            adm_dt = kv(ln, "入院时间")
            if adm_dt is not None and DT_RE.fullmatch(adm_dt):
                found.add("入院时间")
                card.patient.admission_date = _fv(adm_dt, "入院时间：" + adm_dt, p)
                card.timeline.append(TimelineEvent(
                    event="入院", time=_fv(adm_dt, "入院时间：" + adm_dt, p), source_part=p))
                continue
            rec_dt = kv(ln, "记录时间")
            if rec_dt is not None and DT_RE.fullmatch(rec_dt):
                found.add("记录时间")
                record_time = rec_dt
                card.timeline.append(TimelineEvent(
                    event="入院记录完成", time=_fv(rec_dt, "记录时间：" + rec_dt, p), source_part=p))
                continue
            dx = kv(ln, "入院诊断")
            if dx is not None:
                found.add("入院诊断")
                # icd10 为知识派生字段（部件文本不含 ICD 编码）：解析层置 None，M3 知识库补齐
                card.diagnoses.append(Diagnosis(type="入院", name=_fv(dx, "入院诊断：" + dx, p)))
                continue
            m = _RESIDENT_RE.match(ln)
            if m:
                found.add("记录者")
                card.signatures.append(Signature(
                    role="住院医师", name=_fv(m.group(1), ln, p),
                    date=_fv(record_time[:10], "记录时间：" + record_time, p) if record_time else None))
                continue
            for key in ("主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊疗计划"):
                if kv(ln, key) is not None:
                    found.add(key)  # 仅必备区块存在性校验，值不入参数卡
                    break

        for key in _REQUIRED_KEYS:
            if key not in found:
                card.parse_warnings.append("入院记录缺少区块：%s" % key)
        return card
