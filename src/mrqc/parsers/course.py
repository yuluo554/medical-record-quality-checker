"""病程记录解析器：节式抽取 → 时间轴事件（首次病程/术前讨论/术后首次/危急值处置/用血审批）。

对照 render._render_course 逐行适配（渲染格式权威）：每节 = 标题行 + 时间行 + 内容行，
节间空行分隔；节按时间升序排版。时间轴证据摘录跨两行（"标题\\n时间"）。
日常病程节仅存在性校验，不入时间轴（渲染真值口径）。术前讨论 detail = 拟施手术名。
"""

import re

from ..models import Evidence, FieldValue, RecordCard, TimelineEvent
from .base import BaseParser, DT_RE, PartType

__all__ = ["CourseParser"]

# 节标题 → 时间轴事件名（None = 不入时间轴）
_SECTION_EVENTS = {
    "首次病程记录": "首次病程记录",
    "术前讨论": "术前讨论",
    "术后首次病程记录": "术后首次病程",
    "危急值处置记录": "危急值处置",
    "输血病程记录": "用血审批",
    "日常病程记录": None,
}

_PLANNED_RE = re.compile(r"拟施手术：(.+?)；")


class CourseParser(BaseParser):
    part = PartType.COURSE

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        p = self.part
        lines = [ln.rstrip() for ln in text.splitlines()]
        current = None  # 当前节标题
        seen_sections = set()

        i = 0
        while i < len(lines):
            ln = lines[i]
            stripped = ln.strip()
            if stripped in _SECTION_EVENTS:
                current = stripped
                seen_sections.add(current)
                event = _SECTION_EVENTS[current]
                time_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if event is not None:
                    if DT_RE.fullmatch(time_line):
                        quote = "%s\n%s" % (stripped, time_line)
                        detail = ""
                        if current == "术前讨论":
                            for j in range(i + 2, len(lines)):
                                m = _PLANNED_RE.search(lines[j])
                                if m:
                                    detail = m.group(1)
                                    break
                        card.timeline.append(TimelineEvent(
                            event=event,
                            time=FieldValue(value=time_line, confidence=1.0,
                                            evidence=[Evidence(part=p, quote=quote)]),
                            source_part=p, detail=detail,
                        ))
                    else:
                        card.parse_warnings.append("病程记录 %s 节缺少时间行" % current)
                i += 2
                continue
            if not stripped:
                i += 1
                continue
            if current is None:
                card.parse_warnings.append("病程记录存在未归属行：%s" % stripped[:40])
                i += 1
                continue
            i += 1

        if "首次病程记录" not in seen_sections:
            card.parse_warnings.append("病程记录缺少区块：首次病程记录")
        return card
