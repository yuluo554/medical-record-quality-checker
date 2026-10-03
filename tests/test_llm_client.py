"""LLM 客户端单测（M4，全离线：_http_post_json 打桩，零 API 依赖）。

覆盖降级纪律：未配置 / 超时 / 重试耗尽 / HTTP 4xx 不重试 / JSON 损坏（含截断）
统一抛 LLMError，由调用方降级纯规则通路；qwen 系 enable_thinking=false；
截断修复只回收已完整闭合的前缀元素。
"""

import json
import socket
import urllib.error

import pytest

from mrqc.llm.client import (
    DEFAULT_TIMEOUT,
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    ENV_TIMEOUT,
    LLMClient,
    LLMError,
    llm_available,
    repair_truncated_json,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL, ENV_TIMEOUT):
        monkeypatch.delenv(key, raising=False)


def _client(**kw):
    kw.setdefault("base_url", "http://mock/v1")
    kw.setdefault("api_key", "test-key")
    kw.setdefault("model", "qwen-plus")
    kw.setdefault("timeout", 1)
    kw.setdefault("retries", 2)
    kw.setdefault("backoff", 0)  # 测试零等待
    return LLMClient(**kw)


def _ok(content):
    return {"choices": [{"message": {"content": content}}]}


# ---------------------------------------------------------------- 配置与环境

def test_llm_available_requires_all_env(monkeypatch):
    assert not llm_available()
    monkeypatch.setenv(ENV_BASE_URL, "http://x")
    monkeypatch.setenv(ENV_API_KEY, "k")
    assert not llm_available()  # 缺 MODEL
    monkeypatch.setenv(ENV_MODEL, "qwen-plus")
    assert llm_available()


def test_chat_unconfigured_raises_llm_error():
    with pytest.raises(LLMError) as exc:
        LLMClient().chat([{"role": "user", "content": "hi"}])
    assert "MRQC_LLM_BASE_URL" in str(exc.value)


def test_timeout_env_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv(ENV_TIMEOUT, "abc")
    assert LLMClient().timeout == DEFAULT_TIMEOUT
    monkeypatch.setenv(ENV_TIMEOUT, "5")
    assert LLMClient().timeout == 5.0


# ---------------------------------------------------------------- 请求契约

def test_chat_posts_openai_compatible_payload(monkeypatch):
    captured = {}

    def fake(url, headers, body, timeout):
        captured.update(url=url, headers=headers, body=json.loads(body.decode("utf-8")))
        return _ok('{"ok": true}')

    monkeypatch.setattr("mrqc.llm.client._http_post_json", fake)
    out = _client().chat([{"role": "user", "content": "抽取"}])
    assert json.loads(out) == {"ok": True}
    assert captured["url"] == "http://mock/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["body"]["model"] == "qwen-plus"
    assert captured["body"]["messages"] == [{"role": "user", "content": "抽取"}]
    assert captured["body"]["enable_thinking"] is False  # qwen 系必须关思考模式


def test_chat_non_qwen_omits_enable_thinking(monkeypatch):
    captured = {}

    def fake(url, headers, body, timeout):
        captured["body"] = json.loads(body.decode("utf-8"))
        return _ok('{"ok": true}')

    monkeypatch.setattr("mrqc.llm.client._http_post_json", fake)
    _client(model="gpt-4o").chat([{"role": "user", "content": "hi"}])
    assert "enable_thinking" not in captured["body"]  # 严格端点兼容：非 qwen 不带该字段


def test_chat_max_tokens_passthrough(monkeypatch):
    captured = {}

    def fake(url, headers, body, timeout):
        captured["body"] = json.loads(body.decode("utf-8"))
        return _ok('{"ok": true}')

    monkeypatch.setattr("mrqc.llm.client._http_post_json", fake)
    _client().chat([{"role": "user", "content": "hi"}], max_tokens=512)
    assert captured["body"]["max_tokens"] == 512


# ---------------------------------------------------------------- 失败路径（降级纪律）

def test_chat_retries_on_timeout_then_succeeds(monkeypatch):
    attempts = []

    def flaky(url, headers, body, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise socket.timeout("timed out")
        return _ok('{"ok": 1}')

    monkeypatch.setattr("mrqc.llm.client._http_post_json", flaky)
    assert json.loads(_client().chat([{"role": "user", "content": "hi"}])) == {"ok": 1}
    assert len(attempts) == 3


def test_chat_raises_after_retries_exhausted(monkeypatch):
    attempts = []

    def down(url, headers, body, timeout):
        attempts.append(1)
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("mrqc.llm.client._http_post_json", down)
    with pytest.raises(LLMError) as exc:
        _client(retries=2).chat([{"role": "user", "content": "hi"}])
    assert len(attempts) == 3  # retries=2 → 共 3 次尝试
    assert "重试耗尽" in str(exc.value)


def test_chat_no_retry_on_http_4xx(monkeypatch):
    attempts = []

    def unauthorized(url, headers, body, timeout):
        attempts.append(1)
        raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)

    monkeypatch.setattr("mrqc.llm.client._http_post_json", unauthorized)
    with pytest.raises(LLMError) as exc:
        _client().chat([{"role": "user", "content": "hi"}])
    assert len(attempts) == 1  # 业务性 4xx 不重试
    assert "401" in str(exc.value)


@pytest.mark.parametrize("code", [429, 500, 503])
def test_chat_retries_on_429_and_5xx(monkeypatch, code):
    attempts = []

    def server_error(url, headers, body, timeout):
        attempts.append(1)
        raise urllib.error.HTTPError(url, code, "err", None, None)

    monkeypatch.setattr("mrqc.llm.client._http_post_json", server_error)
    with pytest.raises(LLMError):
        _client(retries=1).chat([{"role": "user", "content": "hi"}])
    assert len(attempts) == 2  # 429/5xx 可重试


def test_chat_backoff_sleeps_between_attempts(monkeypatch):
    sleeps = []
    monkeypatch.setattr("mrqc.llm.client.time.sleep", lambda s: sleeps.append(s))

    def down(url, headers, body, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("mrqc.llm.client._http_post_json", down)
    with pytest.raises(LLMError):
        _client(retries=2, backoff=0.5).chat([{"role": "user", "content": "hi"}])
    assert sleeps == [0.5, 1.0]


def test_chat_missing_content_raises(monkeypatch):
    monkeypatch.setattr("mrqc.llm.client._http_post_json",
                        lambda *a: {"choices": []})
    with pytest.raises(LLMError):
        _client().chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------- JSON 修复

def test_chat_json_mode_returns_parseable_json(monkeypatch):
    monkeypatch.setattr("mrqc.llm.client._http_post_json",
                        lambda *a: _ok('{"extractions": [{"field": "a"}]}'))
    out = _client().chat([{"role": "user", "content": "hi"}])
    assert json.loads(out)["extractions"][0]["field"] == "a"


def test_chat_json_mode_repairs_truncated(monkeypatch):
    truncated = '{"extractions": [{"field": "labs[0].item_name", "value": "胸部正位片"}, {"field": "tr'
    monkeypatch.setattr("mrqc.llm.client._http_post_json", lambda *a: _ok(truncated))
    out = _client().chat([{"role": "user", "content": "hi"}])
    obj = json.loads(out)  # 修复后必须可解析：前缀对象回收，半个尾对象丢弃
    assert obj["extractions"] == [{"field": "labs[0].item_name", "value": "胸部正位片"}]


def test_chat_json_mode_unrepairable_raises(monkeypatch):
    monkeypatch.setattr("mrqc.llm.client._http_post_json",
                        lambda *a: _ok("抱歉，我无法输出结构化结果。"))
    with pytest.raises(LLMError) as exc:
        _client().chat([{"role": "user", "content": "hi"}])
    assert "不可解析" in str(exc.value)


def test_chat_json_mode_false_returns_raw(monkeypatch):
    monkeypatch.setattr("mrqc.llm.client._http_post_json", lambda *a: _ok("纯文本回复"))
    assert _client().chat([{"role": "user", "content": "hi"}], json_mode=False) == "纯文本回复"


def test_repair_passthrough_valid_json():
    assert repair_truncated_json('{"a": 1}') == {"a": 1}
    assert repair_truncated_json('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}  # 围栏剥离
    assert repair_truncated_json('  [1, 2, 3]  ') == [1, 2, 3]


def test_repair_salvages_closed_prefix():
    # 数组中部截断：已闭合对象回收，半个尾对象丢弃
    assert repair_truncated_json('{"xs": [{"a": 1}, {"b": 2}, {"c": 3') == \
        {"xs": [{"a": 1}, {"b": 2}]}
    # 字符串中段截断：退回上一个逗号前的完整前缀
    assert repair_truncated_json('{"a": 1, "b": "he') == {"a": 1}
    # 数组标量截断：尾部标量可能是被截断的数字，保守丢弃只回收有逗号证明完整的
    assert repair_truncated_json('{"a": [1, 2') == {"a": [1]}
    # 前置说明文字 + 截断
    assert repair_truncated_json('结果如下：{"a": [{"x": "y"}, {"z": "w"') == \
        {"a": [{"x": "y"}]}


def test_repair_unsalvageable_returns_none():
    assert repair_truncated_json('{"a": "无闭合') is None  # 首个对象都没闭合
    assert repair_truncated_json("") is None
    assert repair_truncated_json(None) is None
    assert repair_truncated_json("不是 JSON") is None
