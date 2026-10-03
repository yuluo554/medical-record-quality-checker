"""解析层：六类病历部件 → 病历参数卡（M2）。

部件识别 → 按固定部件顺序分发给已注册解析器 → 累加成一张 RecordCard。
解析全程不抛异常：未识别部件/缺区块/未识别行一律记 parse_warnings。
"""

import pathlib
from typing import Dict, List, Tuple, Type

from .base import BaseParser, PartType, detect_part
from .course import CourseParser
from .discharge import DischargeParser
from .labs import LabParser
from .orders import OrderParser
from .admission import AdmissionParser
from .surgery import SurgeryParser

__all__ = ["PartType", "BaseParser", "detect_part", "PARSERS", "PART_ORDER",
           "load_part_texts", "parse_record_dir", "parse_texts", "registered_parts"]

# 部件名 → 解析器类（M2 全部注册）
PARSERS: Dict[str, Type[BaseParser]] = {
    PartType.ADMISSION: AdmissionParser,
    PartType.COURSE: CourseParser,
    PartType.SURGERY: SurgeryParser,
    PartType.DISCHARGE: DischargeParser,
    PartType.ORDERS: OrderParser,
    PartType.LABS: LabParser,
}

# 部件处理顺序 = 渲染装配顺序（决定参数卡内列表的拼接序，与真值对齐的关键）
PART_ORDER = (PartType.ADMISSION, PartType.COURSE, PartType.SURGERY,
              PartType.DISCHARGE, PartType.ORDERS, PartType.LABS)


def load_part_texts(input_dir) -> Tuple[Dict[str, str], List[str]]:
    """读取病历部件目录（*.txt），按标题关键词识别部件。

    返回（部件名 → 文本，按 PART_ORDER 排序；告警列表）。无法识别/重复部件记告警。
    """
    warnings: List[str] = []
    by_part: Dict[str, Tuple[str, str]] = {}  # part -> (文件名, 文本)
    input_dir = pathlib.Path(input_dir)
    if not input_dir.is_dir():
        return {}, ["输入目录不存在：%s" % input_dir]
    for path in sorted(input_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        part = detect_part(text)
        if part is None:
            warnings.append("无法识别部件：%s" % path.name)
            continue
        if part in by_part:
            warnings.append("部件重复：%s（%s 已识别为 %s）" % (path.name, by_part[part][0], part))
            continue
        by_part[part] = (path.name, text)
    ordered = {part: by_part[part][1] for part in PART_ORDER if part in by_part}
    return ordered, warnings


def parse_texts(part_texts: Dict[str, str]) -> "object":
    """部件名 → 文本 字典 → RecordCard（parse_record_dir 的纯函数内核）。"""
    from ..models import RecordCard  # 局部导入避免循环

    card = RecordCard()
    for part in PART_ORDER:
        text = part_texts.get(part)
        if text is None:
            continue  # 部件可缺失（CAP 无手术记录属正常，不告警）
        parser_cls = PARSERS.get(part)
        if parser_cls is None:
            card.parse_warnings.append("%s 解析器未注册" % part)
            continue
        card = parser_cls().parse(text, card)
    # 时间轴按时间升序（value 为 "YYYY-MM-DD HH:MM"，字典序即时间序；与渲染真值同口径）
    card.timeline.sort(key=lambda ev: (ev.time.value if ev.time else "", ev.event))
    return card


def parse_record_dir(input_dir) -> "object":
    """解析一份病历的部件集合目录（*.txt）→ RecordCard。"""
    from ..models import RecordCard

    part_texts, warnings = load_part_texts(input_dir)
    card = parse_texts(part_texts)
    card.parse_warnings[:0] = warnings  # 目录级告警排前
    return card


def registered_parts() -> List[str]:
    return sorted(PARSERS)
