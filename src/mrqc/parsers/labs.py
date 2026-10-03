"""检验检查报告解析器：节式（【类别】+报告时间）+ 条目行 → LabResult。

对照 render._render_labs 逐行适配（渲染格式权威）：
  数值条目 = "项目 数值 单位 ↑↓|正常（[危急值，]参考范围 …）"
  文本条目 = "检查所见：…"（影像/心电图；渲染只落检查所见不落项目名，
  item_name 记报告类别、置信度降档标注，M3 知识库可精化——基准口径见 eval/parse_f1）。
"""

import re

from ..models import Evidence, FieldValue, LabResult, RecordCard
from .base import BaseParser, DT_RE, PartType

__all__ = ["LabParser"]

_CATEGORY_RE = re.compile(r"【(.+?)】")
_ITEM_RE = re.compile(
    r"^(?P<item>.+?) (?P<value>\d+(?:\.\d+)?) (?P<unit>\S+) (?P<flag>↑|↓|正常)"
    r"（(?P<crit>危急值，)?参考范围 (?P<ref>[^）]+)）$")


def _fv(value, quote: str, part: str, confidence: float = 1.0) -> FieldValue:
    return FieldValue(value=value, confidence=confidence,
                      evidence=[Evidence(part=part, quote=quote)])


class LabParser(BaseParser):
    part = PartType.LABS

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        p = self.part
        category = ""
        report_time = ""
        report_time_line = ""
        item_count = 0

        for ln in [l.rstrip() for l in text.splitlines()]:
            if not ln.strip() or ln.startswith("检验检查报告"):
                continue
            m = _CATEGORY_RE.fullmatch(ln.strip())
            if m:
                category = m.group(1)
                report_time = ""
                continue
            if ln.startswith("报告时间："):
                rt = ln[len("报告时间："):]
                if DT_RE.fullmatch(rt):
                    report_time = rt
                    report_time_line = ln
                    continue
            if ln.startswith("检查所见："):
                if not report_time:
                    card.parse_warnings.append("检验检查报告 %s 条目缺少报告时间" % (category or "?"))
                card.labs.append(LabResult(
                    item_name=_fv(category, ln, p, confidence=0.6),  # 项目名不落文本，记报告类别
                    value_text=_fv(ln[len("检查所见："):], ln, p),
                    report_time=_fv(report_time, report_time_line, p) if report_time else None,
                ))
                item_count += 1
                continue
            m = _ITEM_RE.match(ln)
            if m:
                if not report_time:
                    card.parse_warnings.append("检验检查报告 %s 条目缺少报告时间" % (category or "?"))
                card.labs.append(LabResult(
                    item_name=_fv(m.group("item"), ln, p),
                    value=_fv(m.group("value"), ln, p),
                    unit=_fv(m.group("unit"), ln, p),
                    abnormal_flag=_fv(m.group("flag"), ln, p),
                    is_critical=_fv(m.group("crit") == "危急值，", ln, p),
                    report_time=_fv(report_time, report_time_line, p) if report_time else None,
                ))
                item_count += 1
                continue
            card.parse_warnings.append("检验检查报告未识别行：%s" % ln)

        if item_count == 0:
            card.parse_warnings.append("检验检查报告缺少条目")
        return card
