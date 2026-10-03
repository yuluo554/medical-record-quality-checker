"""确定性随机源：位级可复现的基石。

Python 官方只保证 `random.Random.random()` 在同 seed 下跨版本产生相同序列
（randint/choice/shuffle/sample 的内部实现可能在版本间变化）。本生成器的
位级可复现纪律（同 seed 重跑 git status 零变化）要求全部随机派生只经由
random() 一个原语，因此自行实现 below/choice/randint/shuffle/pick。
"""

import random
from typing import List, Sequence, TypeVar

__all__ = ["DetRng"]

T = TypeVar("T")

_MINUTE_SLOTS = (0, 15, 30, 45)


class DetRng:
    """确定性随机源（只消费 random()，跨 3.8/3.10/3.12 稳定）。"""

    def __init__(self, seed: int) -> None:
        self._rnd = random.Random(seed)

    def random(self) -> float:
        return self._rnd.random()

    def below(self, n: int) -> int:
        """返回 [0, n) 的整数。"""
        if n <= 0:
            raise ValueError("below() 需要 n>0，收到 %r" % n)
        return int(self._rnd.random() * n) % n

    def choice(self, seq: Sequence[T]) -> T:
        return seq[self.below(len(seq))]

    def randint(self, lo: int, hi: int) -> int:
        """返回 [lo, hi] 的整数（含端点）。"""
        if hi < lo:
            raise ValueError("randint(%r, %r) 上界小于下界" % (lo, hi))
        return lo + self.below(hi - lo + 1)

    def shuffle(self, seq: List[T]) -> None:
        """Fisher-Yates 原地洗牌。"""
        for i in range(len(seq) - 1, 0, -1):
            j = self.below(i + 1)
            seq[i], seq[j] = seq[j], seq[i]

    def pick(self, seq: Sequence[T], k: int) -> List[T]:
        """不重复取 k 项（洗牌副本取前 k）。"""
        if k > len(seq):
            raise ValueError("pick(%r) 超出池大小 %d" % (k, len(seq)))
        pool = list(seq)
        self.shuffle(pool)
        return pool[:k]

    def chance(self, p: float) -> bool:
        return self._rnd.random() < p

    def minute_slot(self) -> int:
        """分钟取整到 0/15/30/45（病历时间惯例，且利于跨记录去重）。"""
        return _MINUTE_SLOTS[self.below(4)]
