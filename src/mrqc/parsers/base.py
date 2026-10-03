"""解析层接口：部件识别 + 解析器基类 + 行式抽取共用工具。

解析器（M2）：规则优先——正则+槽位+合法性校验，LLM 只兜底低置信度字段（M4）。
渲染格式权威 = datagen/render.py：本层所有正则/抽取逻辑对照渲染实现逐行适配，
改渲染必须同步解析（并重生成数据集 + 位级复现测试全过）。
"""

import re
from typing import ClassVar, Optional

from ..models import RecordCard

__all__ = ["PartType", "BaseParser", "detect_part", "DT_RE", "match_dt", "kv"]

# "YYYY-MM-DD HH:MM"（生成器唯一时间格式，_fmt_hm 口径）
DT_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def match_dt(text: str) -> Optional[str]:
    """取字符串中的首个日期时间（无则 None）。"""
    m = DT_RE.search(text)
    return m.group(0) if m else None


def kv(line: str, key: str) -> Optional[str]:
    """行首键值抽取："键：值…" 返回值部分（不含键冒号）；非该键行返回 None。"""
    prefix = key + "："
    if line.startswith(prefix):
        return line[len(prefix):]
    return None


class PartType:
    """六类病历部件（值即部件中文名，用作证据里的 part 字段）。"""

    ADMISSION = "入院记录"
    COURSE = "病程记录"
    SURGERY = "手术记录"
    DISCHARGE = "出院记录"
    ORDERS = "医嘱单"
    LABS = "检验检查报告"

    ALL = (ADMISSION, COURSE, SURGERY, DISCHARGE, ORDERS, LABS)


# 部件标题关键词（带优先级的匹配表，按 PartType.ALL 顺序；M2 实测锁定）
_PART_KEYWORDS = {
    PartType.ADMISSION: ("入院记录",),
    PartType.COURSE: ("首次病程记录", "日常病程记录", "术前讨论", "术后首次病程记录", "病程记录"),
    PartType.SURGERY: ("手术记录",),
    PartType.DISCHARGE: ("出院记录", "出院小结"),
    PartType.ORDERS: ("长期医嘱单", "临时医嘱单", "医嘱单"),
    PartType.LABS: ("检验检查报告", "检验报告", "检查报告"),
}


def detect_part(text: str) -> Optional[str]:
    """按标题关键词识别部件归属；无法识别返回 None（计入解析告警）。"""
    head = text.lstrip()[:120]
    for part, keywords in _PART_KEYWORDS.items():
        for kw in keywords:
            if head.startswith(kw) or (kw in head and head.index(kw) < 40):
                return part
    return None


class BaseParser:
    """部件解析器基类：parse(text, card) -> card（向参数卡累加字段）。"""

    part: ClassVar[str] = ""

    def parse(self, text: str, card: RecordCard) -> RecordCard:
        raise NotImplementedError(
            "%s 解析器在 M2 实现（plan/05 里程碑 M2）" % (self.part or type(self).__name__)
        )
