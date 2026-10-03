"""LLM 兜底客户端（OpenAI 兼容端点，stdlib urllib 实现，无第三方依赖）。

职责白名单（plan/03 §5）：低置信度字段抽取兜底 / 别名归一 / 结论复核 / 报告行文。
数值结论永远来自确定性规则。

防幻觉三件套（实现在 fallback.py）：候选行压缩 / 摘录逐字回验 / 数值合法性校验。

降级纪律（M4 定稿）：本客户端任何失败——未配置、网络超时、重试耗尽、HTTP 4xx
（业务性错误）、JSON 不可解析——统一抛 :class:`LLMError`，由调用方捕获后走纯规则
通路。LLM 只锦上添花，绝不阻塞质控主流程；基准与测试零 API 依赖（全部 mock，
环境未配置即等效纯规则环境）。

截断修复纪律（repair_truncated_json）：max_tokens 截断的 JSON 流只回收"已完整
闭合的前缀元素"——从最长的闭合点候选截断、补齐未闭合容器后能解析即回收；
连一个完整元素都凑不出则整体丢弃交降级路径。绝不猜测/补全缺失的字段或键
（截断尾部的半个对象直接丢弃，与 fallback 的契约逐条校验构成双保险）。
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, List, Optional

__all__ = ["LLMError", "LLMClient", "llm_available", "repair_truncated_json"]

ENV_BASE_URL = "MRQC_LLM_BASE_URL"
ENV_API_KEY = "MRQC_LLM_API_KEY"
ENV_MODEL = "MRQC_LLM_MODEL"
ENV_TIMEOUT = "MRQC_LLM_TIMEOUT"

DEFAULT_TIMEOUT = 60.0
DEFAULT_RETRIES = 2  # 首次失败后再试 2 次（共 3 次尝试）
DEFAULT_BACKOFF = 0.5  # 退避基数（秒）：第 n 次重试前睡 backoff * n


def llm_available() -> bool:
    """环境变量是否配置齐全（BASE_URL / API_KEY / MODEL）。"""
    return bool(
        os.getenv(ENV_BASE_URL) and os.getenv(ENV_API_KEY) and os.getenv(ENV_MODEL)
    )


class LLMError(RuntimeError):
    """LLM 调用失败（未配置/超时/重试耗尽/HTTP 错误/JSON 不可解析）。

    调用方捕获后应降级纯规则通路，而不是让主流程失败。
    （继承 RuntimeError 兼容骨架期 raise RuntimeError 的调用方约定。）
    """


def _env_timeout() -> float:
    raw = os.getenv(ENV_TIMEOUT, "")
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT
    except ValueError:
        return DEFAULT_TIMEOUT


def _scan_json_prefix(s: str) -> List:
    """字符串感知扫描截断流，返回候选闭合点 (位置, 括号栈, 顶层起点) 列表。

    候选 = 内层容器刚闭合的位置（栈非空）+ 栈非空时每个逗号前的位置
    （丢掉残缺尾元素）。调用方从最长候选试起：截断 + 补齐闭合符后能解析即回收。
    """
    stack = []
    in_str = False
    esc = False
    top_start = -1
    cuts = []
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            if not stack:
                top_start = i
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break  # 结构破坏（截断点之后不该再有闭括号），以已扫前缀为准
            stack.pop()
            if stack:
                cuts.append((i + 1, tuple(stack), top_start))
        elif ch == "," and stack:
            cuts.append((i, tuple(stack), top_start))
    return cuts


def repair_truncated_json(text: str) -> Optional[Any]:
    """max_tokens 截断的 JSON 修复：只回收已完整闭合的前缀元素。

    - 剥掉 markdown 代码围栏（右围栏可能被一并截断）后能直接解析就直接返回；
    - 否则按 :func:`_scan_json_prefix` 的候选从最长截断位置试起，
      补齐未闭合容器后能 json.loads 即返回该前缀对象；
    - 全部候选失败返回 None（调用方走降级路径）。

    纪律：不猜测/补全任何缺失字段——截断尾部的半个对象直接丢弃。
    """
    if not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        s = s[3:]
        if s.startswith("json"):
            s = s[4:]
        idx = s.rfind("```")
        if idx != -1:
            s = s[:idx]
        s = s.strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    cuts = _scan_json_prefix(s)
    if len(cuts) > 500:  # 异常长流只试最后的候选（最长优先）
        cuts = cuts[-500:]
    for pos, open_stack, top_start in reversed(cuts):
        closers = "".join("}" if c == "{" else "]" for c in reversed(open_stack))
        try:
            return json.loads(s[top_start:pos] + closers)
        except ValueError:
            continue
    return None


def _http_post_json(url: str, headers: dict, body: bytes, timeout: float) -> dict:
    """stdlib urllib POST → JSON 响应（模块级函数 = 测试 mock 点）。"""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LLMClient:
    """OpenAI 兼容 chat/completions 客户端。

    - 重试：网络错误/超时/HTTP 429/5xx 退避重试（共 retries+1 次尝试）；
      其余 4xx 是业务性错误（密钥/模型名/请求体），不重试直接 LLMError；
    - qwen 系：请求体带 ``enable_thinking=false``（qwen3 系不开即超慢，
      plan/06 LLM 供应商决策）；其他模型不带该字段（兼容严格端点）；
    - json_mode：不传 response_format（OpenAI 兼容端点支持面参差，传了被拒即
      4xx），JSON 约束由提示词（fallback.py）+ 截断修复保障——修复失败抛
      LLMError 降级。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        retries: Optional[int] = None,
        backoff: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or os.getenv(ENV_BASE_URL, "")).rstrip("/")
        self.api_key = api_key or os.getenv(ENV_API_KEY, "")
        self.model = model or os.getenv(ENV_MODEL, "")
        self.timeout = timeout if timeout is not None else _env_timeout()
        self.retries = retries if retries is not None else DEFAULT_RETRIES
        self.backoff = backoff if backoff is not None else DEFAULT_BACKOFF

    def chat(self, messages: List[dict], json_mode: bool = True,
             max_tokens: Optional[int] = None) -> str:
        """发送对话，返回回复文本。

        json_mode=True 时保证返回"可 json.loads 的 JSON 字符串"（截断修复后
        重序列化），修复不了抛 LLMError。任何失败路径都抛 LLMError，不返回 None。
        """
        if not (self.base_url and self.api_key and self.model):
            raise LLMError(
                "LLM 未配置：请设置 %s / %s / %s 环境变量，"
                "或使用纯规则通路（未配置时流水线自动降级）"
                % (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL)
            )
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0.0,  # 抽取兜底要确定性输出
        }
        if "qwen" in self.model.lower():
            payload["enable_thinking"] = False
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        url = self.base_url + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        last_err = ""
        for attempt in range(1, self.retries + 2):
            if attempt > 1:
                time.sleep(self.backoff * (attempt - 1))
            try:
                data = _http_post_json(url, headers, body, self.timeout)
            except urllib.error.HTTPError as exc:
                # HTTPError ⊂ URLError ⊂ OSError，必须先于 OSError 捕获
                if exc.code != 429 and exc.code < 500:
                    raise LLMError(
                        "LLM 端点返回 HTTP %d（不重试，请检查 BASE_URL/API_KEY/MODEL）：%s"
                        % (exc.code, exc.reason)
                    )
                last_err = "HTTP %d：%s" % (exc.code, exc.reason)
            except OSError as exc:  # URLError / socket.timeout / 连接复位
                last_err = "网络错误或超时：%s" % exc
            else:
                return self._extract_content(data, json_mode)
        raise LLMError("LLM 调用重试耗尽（共 %d 次尝试）：%s" % (self.retries + 1, last_err))

    @staticmethod
    def _extract_content(data: dict, json_mode: bool) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("LLM 响应缺 choices[0].message.content：%s" % str(data)[:200])
        if not isinstance(content, str):
            raise LLMError("LLM 响应 content 非字符串：%r" % (content,))
        if not json_mode:
            return content
        repaired = repair_truncated_json(content)
        if repaired is None:
            raise LLMError("LLM 输出 JSON 不可解析（截断修复失败）：%s" % content[:200])
        return json.dumps(repaired, ensure_ascii=False)
