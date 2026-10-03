"""Web 面板测试：0 外链静态断言、路由行为（直调端点）、真实 uvicorn multipart 上传冒烟。

纪律：
- 不用 starlette TestClient（httpx 是未声明依赖，CI 缺失会静默少跑）——
  单元级直调路由端点函数；HTTP 层（multipart 解析/python-multipart 运行期依赖）
  由真实 uvicorn 子进程冒烟覆盖；
- 真实冒烟依赖 web extra（uvicorn），缺失时显式原因跳过；CI 安装全量 extras 必跑。
"""

import asyncio
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from mrqc.web import _DISCLAIMER, _PAGE_HTML

REPO_ROOT = Path(__file__).resolve().parents[1]
fastapi = pytest.importorskip("fastapi", reason="web extra 未安装：pip install 'mrqc[web]'")

from mrqc.web import create_app  # noqa: E402  需 fastapi，置于 importorskip 之后


# ---------- 静态断言（不依赖 fastapi 也能跑） ----------

def test_page_html_has_zero_external_links():
    """页面 0 外链：断网可演示的硬性纪律。"""
    assert "http://" not in _PAGE_HTML and "https://" not in _PAGE_HTML
    for banned in ("<link", "script src", "@import", "url("):
        assert banned not in _PAGE_HTML, "页面禁止外链引用：%s" % banned
    assert "不是临床决策支持工具" in _PAGE_HTML  # 免责声明保留


def test_page_html_inline_style_and_script():
    assert "<style>" in _PAGE_HTML and "<script>" in _PAGE_HTML


# ---------- 路由行为（直调端点函数，绕过 HTTP 层） ----------

def _route(app, path):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route
    raise AssertionError("路由缺失：%s" % path)


def test_docs_and_redoc_disabled():
    """/docs、/redoc、openapi 显式关闭（Swagger UI 引 CDN，破坏 0 外链）。"""
    app = create_app()
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_index_route_returns_inline_html():
    app = create_app()
    resp = _route(app, "/").endpoint()
    assert resp.status_code == 200
    assert "病历内涵质控" in resp.body.decode("utf-8")


def test_status_route_shape():
    app = create_app()
    data = _route(app, "/api/status").endpoint()  # 直调端点：返回 dict（HTTP 层才转 JSON）
    assert data["version"]
    assert isinstance(data["n_rules"], int) and data["n_rules"] > 0
    assert data["llm_available"] in (True, False)
    assert "不是临床决策支持工具" in data["disclaimer"]


def _upload(name: str, text: str):
    from starlette.datastructures import UploadFile

    return UploadFile(file=io.BytesIO(text.encode("utf-8")), filename=name)


def test_check_endpoint_with_uploaded_parts():
    """直调端点：真实部件文本上传 → 结论 JSON（summary/findings/告警/耗时）。"""
    rec = REPO_ROOT / "data" / "paired" / "defect_C-LAB-02_01"
    files = [_upload(p.name, p.read_text(encoding="utf-8"))
             for p in sorted(rec.glob("*.txt"))]
    app = create_app()
    resp = asyncio.run(_route(app, "/api/check").endpoint(files=files))
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert data["summary"]["overall"] == "fail"  # 缺陷记录必出非 pass
    assert data["summary"]["n_rules"] == 33
    non_pass = [f for f in data["findings"] if f["status"] != "pass"]
    assert non_pass and all(f["basis"] for f in non_pass)  # 依据关联
    assert "不是临床决策支持工具" in data["disclaimer"]
    assert set(data["timings"]) == {"解析", "LLM兜底", "质控", "汇总", "导出"}


# ---------- 真实 uvicorn 上传冒烟（HTTP 层 + python-multipart 运行期依赖） ----------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _multipart_body(files) -> bytes:
    boundary = "----mrqcsmoketest"
    chunks = []
    for fname, text in files:
        chunks.append(("--%s\r\nContent-Disposition: form-data; name=\"files\"; "
                       "filename=\"%s\"\r\nContent-Type: text/plain\r\n\r\n"
                       % (boundary, fname)).encode("utf-8"))
        chunks.append(text.encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(chunks), boundary


def test_real_uvicorn_multipart_smoke(tmp_path):
    """姊妹项目教训：multipart 缺依赖/上传路径不通只有实跑才发现。

    起真实 uvicorn（py -m mrqc.web）→ GET / 与 /api/status → multipart POST
    /api/check（stdlib urllib 手工构造 multipart 体）→ 断言结论 JSON。
    """
    pytest.importorskip("uvicorn", reason="web extra 未安装：pip install 'mrqc[web]'")
    pytest.importorskip("multipart", reason="python-multipart 未安装（web extra）")
    port = _free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "mrqc.web",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    try:
        # 轮询启动（最长 30s）
        deadline = time.time() + 30
        while True:
            try:
                with urllib.request.urlopen(base + "/api/status", timeout=2) as resp:
                    assert resp.status == 200
                break
            except Exception:  # noqa: BLE001 —— 启动期轮询
                if time.time() > deadline:
                    raise
                time.sleep(0.3)
        # 首页可取（单页 HTML，0 外链断网可演示）
        with urllib.request.urlopen(base + "/", timeout=5) as resp:
            page = resp.read().decode("utf-8")
        assert "病历内涵质控" in page
        assert "http://" not in page and "https://" not in page
        # 真实 multipart 上传（缺陷记录部件 → 应出非 pass 结论）
        rec = REPO_ROOT / "data" / "paired" / "defect_C-LAB-02_01"
        files = [(p.name, p.read_text(encoding="utf-8")) for p in sorted(rec.glob("*.txt"))]
        body, boundary = _multipart_body(files)
        req = urllib.request.Request(
            base + "/api/check", data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        with urllib.request.urlopen(req, timeout=30) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
        assert data["summary"]["overall"] == "fail"
        assert data["summary"]["n_rules"] == 33
        assert any(f["status"] != "pass" for f in data["findings"])
    finally:
        proc.terminate()
        proc.wait(timeout=10)
