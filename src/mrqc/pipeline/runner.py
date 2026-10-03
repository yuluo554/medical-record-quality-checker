"""编排层：轻量状态机——节点注册 → 顺序执行 → 耗时记录 → 失败即停。

端到端流水线（plan/03 §6）：解析 → LLM 兜底（可选）→ 质控 → 汇总 → 导出。
"""

import time
import traceback
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

__all__ = ["NodeResult", "Pipeline"]

# 上下文键约定（各节点经 ctx 传递中间产物）
CTX_CARD = "card"  # RecordCard
CTX_PART_TEXTS = "part_texts"  # 部件名 → 原文
CTX_FINDINGS = "findings"  # List[Finding]
CTX_TIMINGS = "timings"  # 节点耗时汇总


@dataclass
class NodeResult:
    name: str
    seconds: float
    ok: bool
    error: str = ""


class Pipeline:
    """节点化流水线。任一节点抛异常：记录失败、停止后续节点、保留已完成结果。"""

    def __init__(self, name: str = "mrqc") -> None:
        self.name = name
        self._nodes: List[str] = []
        self._fns: Dict[str, Callable[[dict], None]] = {}
        self.results: List[NodeResult] = []
        self.success: Optional[bool] = None

    def add_node(self, name: str, fn: Callable[[dict], None]) -> "Pipeline":
        """注册节点。fn(ctx) 就地修改/读取上下文；重复节点名拒绝注册。"""
        if name in self._fns:
            raise ValueError("节点重复注册：%s" % name)
        self._nodes.append(name)
        self._fns[name] = fn
        return self

    def run(self, ctx: Optional[dict] = None) -> dict:
        """执行流水线；返回上下文 ctx。结果明细在 self.results / self.success。"""
        ctx = ctx if ctx is not None else {}
        ctx.setdefault(CTX_TIMINGS, {})
        self.results = []
        self.success = None
        for name in self._nodes:
            fn = self._fns[name]
            start = time.perf_counter()
            try:
                fn(ctx)
                seconds = time.perf_counter() - start
                self.results.append(NodeResult(name=name, seconds=seconds, ok=True))
                ctx[CTX_TIMINGS][name] = seconds
            except Exception as exc:  # noqa: BLE001 —— 编排层兜底记录，异常信息入结果
                seconds = time.perf_counter() - start
                self.results.append(
                    NodeResult(
                        name=name,
                        seconds=seconds,
                        ok=False,
                        error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                    )
                )
                ctx[CTX_TIMINGS][name] = seconds
                self.success = False
                return ctx
        self.success = True
        return ctx
