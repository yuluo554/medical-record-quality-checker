"""LLM 兜底客户端（OpenAI 兼容端点，stdlib urllib 实现，无第三方依赖）。

职责白名单（plan/03 §5）：低置信度字段抽取兜底 / 别名归一 / 结论复核 / 报告行文。
数值结论永远来自确定性规则。

防幻觉三件套（M4 实现）：
1. 候选行压缩：只送含数字/关键词的行，控制成本；
2. 摘录回验：要求返回"原文编号+逐字摘录"，摘录不是原文子串即丢弃；
3. 数值合法性校验：超生理/药理范围的数值直接丢弃。

配置全部走环境变量；未配置 → available() 为 False → 流水线自动走纯规则通路。
"""

import os
from typing import List, Optional

__all__ = ["LLMClient", "llm_available"]

ENV_BASE_URL = "MRQC_LLM_BASE_URL"
ENV_API_KEY = "MRQC_LLM_API_KEY"
ENV_MODEL = "MRQC_LLM_MODEL"
ENV_TIMEOUT = "MRQC_LLM_TIMEOUT"


def llm_available() -> bool:
    """环境变量是否配置齐全（BASE_URL / API_KEY / MODEL）。"""
    return bool(
        os.getenv(ENV_BASE_URL) and os.getenv(ENV_API_KEY) and os.getenv(ENV_MODEL)
    )


class LLMClient:
    """OpenAI 兼容 chat/completions 客户端。

    qwen 系注意：请求体带 enable_thinking=false（qwen3 系不开即超慢）。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = base_url or os.getenv(ENV_BASE_URL, "")
        self.api_key = api_key or os.getenv(ENV_API_KEY, "")
        self.model = model or os.getenv(ENV_MODEL, "")
        self.timeout = timeout if timeout is not None else float(os.getenv(ENV_TIMEOUT, "60"))

    def chat(self, messages: List[dict], json_mode: bool = True) -> str:
        """发送对话，返回回复文本。json_mode 时要求并修复 JSON 输出（M4 实现）。"""
        if not (self.base_url and self.api_key and self.model):
            raise RuntimeError(
                "LLM 未配置：请设置 %s / %s / %s 环境变量，"
                "或使用纯规则通路（未配置时流水线自动降级）"
                % (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL)
            )
        raise NotImplementedError(
            "LLM 兜底调用在 M4 实现：urllib POST / 重试与超时 / "
            "enable_thinking=false / max_tokens 截断 JSON 修复 / 失败降级规则通路"
        )
