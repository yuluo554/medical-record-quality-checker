"""知识库层：规范原文 → 条文块 → 机器可读规则表（三层）。

- raw/    规范原文 txt（M1 入库，逐份挂来源台账）
- blocks/ 条文块 json（M3；检索用纯 Python 余弦，不引 faiss）
- rules/  规则表 json（M3；加载走 rules.engine.RuleEngine，缺 basis 即拒绝）
"""

import pathlib

__all__ = ["knowledge_dir", "knowledge_status"]


def knowledge_dir() -> pathlib.Path:
    """项目内知识库根目录（仓体内的 data/knowledge）。

    文件位于 src/mrqc/knowledge/，parents[3] 才是仓体根（parents[2] 是 src/）。
    """
    return pathlib.Path(__file__).resolve().parents[3] / "data" / "knowledge"


def knowledge_status() -> dict:
    """知识库三层现状盘点（供 CLI demo/状态展示与测试用）。"""
    root = knowledge_dir()

    def count(sub: str, pattern: str) -> int:
        d = root / sub
        return len(list(d.glob(pattern))) if d.is_dir() else 0

    return {
        "raw": count("raw", "*.txt"),
        "blocks": count("blocks", "*.json"),
        "rules": count("rules", "*.json"),
    }
