"""LLM 兜底层：仅做抽取兜底/别名归一/复核/行文，数值结论永远来自确定性规则。"""

from .client import LLMClient, llm_available

__all__ = ["LLMClient", "llm_available"]
