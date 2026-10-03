"""LLM 兜底层：仅做抽取兜底/别名归一/复核/行文，数值结论永远来自确定性规则。"""

from .client import LLMClient, LLMError, llm_available, repair_truncated_json
from .fallback import apply_fallback

__all__ = ["LLMClient", "LLMError", "llm_available", "repair_truncated_json",
           "apply_fallback"]
