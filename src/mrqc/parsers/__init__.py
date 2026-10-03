"""解析层：六类病历部件 → 病历参数卡。解析器 M2 实现。"""

import pathlib
from typing import Dict, List, Type

from .base import BaseParser, PartType, detect_part

__all__ = ["PartType", "BaseParser", "detect_part", "PARSERS", "parse_record_dir"]

# 部件名 → 解析器类；M2 逐个注册
PARSERS: Dict[str, Type[BaseParser]] = {}


def parse_record_dir(input_dir: pathlib.Path) -> "object":  # 返回 RecordCard（避免循环导入用字符串注解）
    """解析一份病历的部件集合目录（*.txt）。

    M0 行为：部件识别可用、解析器未注册 → 产出仅含 parse_warnings 的参数卡。
    """
    from ..models import RecordCard  # 局部导入避免循环

    card = RecordCard()
    input_dir = pathlib.Path(input_dir)
    if not input_dir.is_dir():
        card.parse_warnings.append("输入目录不存在：%s" % input_dir)
        return card
    for path in sorted(input_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        part = detect_part(text)
        if part is None:
            card.parse_warnings.append("无法识别部件：%s" % path.name)
            continue
        parser_cls = PARSERS.get(part)
        if parser_cls is None:
            card.parse_warnings.append("%s 解析器未注册（M2 实现）" % part)
            continue
        card = parser_cls().parse(text, card)
    return card


def registered_parts() -> List[str]:
    return sorted(PARSERS)
