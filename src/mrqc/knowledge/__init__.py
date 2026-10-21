"""知识库层：规范原文 → 条文块 → 机器可读规则表（三层）。

- raw/         规范原文 txt（M1 入库，逐份挂来源台账；留仓内 data/knowledge/raw，不进 wheel）
- data/blocks/ 条文块 json（M3；检索用纯 Python 余弦，不引 faiss；随 wheel 分发）
- data/rules/  规则表 json（M3；加载走 rules.engine.RuleEngine，缺 basis 即拒绝；随 wheel 分发）

M3 起 blocks/rules 移入包内（`src/mrqc/knowledge/data/`），`knowledge_dir()` 走包内
相对定位，非 editable 安装（wheel）下同样可用；raw 原文仅供源码态测试核对引文，
用 `raw_dir()` 定位。
"""

import pathlib

__all__ = ["knowledge_dir", "knowledge_status", "raw_dir"]


def knowledge_dir() -> pathlib.Path:
    """包内知识库根目录（`src/mrqc/knowledge/data`，随 wheel 分发）。

    从 `__file__` 出发做**包内相对定位**，不依赖仓体布局——pip 装成 wheel 后
    在 site-packages 里同样能找到 blocks/rules。
    """
    return pathlib.Path(__file__).resolve().parent / "data"


def raw_dir() -> pathlib.Path:
    """仓内规范原文目录（`data/knowledge/raw`，仅供源码态测试核对引文）。

    不进 wheel；源码态 parents[3] 是仓体根。
    """
    return pathlib.Path(__file__).resolve().parents[3] / "data" / "knowledge" / "raw"


def knowledge_status() -> dict:
    """知识库三层现状盘点（供 CLI demo/状态展示与测试用）。

    raw 计文件数；blocks/rules 计条目数（块/条，读 json 汇总），
    目录缺失或文件损坏计 0（盘点不抛异常）。
    """
    import json

    root = knowledge_dir()

    def count(sub: str, pattern: str) -> int:
        d = root / sub
        return len(list(d.glob(pattern))) if d.is_dir() else 0

    def count_entries(sub: str, key: str) -> int:
        d = root / sub
        if not d.is_dir():
            return 0
        total = 0
        for path in sorted(d.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items = data.get(key, []) if isinstance(data, dict) else data
            if isinstance(items, list):
                total += len(items)
        return total

    return {
        "raw": count("raw", "*.txt"),
        "blocks": count_entries("blocks", "blocks"),
        "rules": count_entries("rules", "rules"),
    }
