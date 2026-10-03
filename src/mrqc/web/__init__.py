"""Web 面板层（FastAPI 免构建单页，M5）。依赖属可选 extra，惰性导入。

硬性要求（plan/05 M5 DoD）：
- 页面 0 外链：CSS/JS 全内联，不引任何 CDN/字体/图片外链，断网可演示；
- /docs、/redoc 显式关闭（Swagger UI 引 CDN，破坏 0 外链；openapi 一并关闭）；
- 上传走 multipart（python-multipart 是运行期必需依赖，extras 守门锁定）；
- 质控通路复用 pipeline.stages 节点，与 CLI 结论同源。
"""

import tempfile
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..pipeline import CTX_CARD, CTX_FINDINGS, CTX_SUMMARY, CTX_TIMINGS
from ..pipeline.stages import build_pipeline

__all__ = ["create_app", "serve", "web_available"]

_PAGE_TITLE = "mrqc 病历内涵质控"
_DISCLAIMER = ("本系统只做病历书写质量与记录一致性质控，不是临床决策支持工具；"
               "演示数据全部为合成数据，不构成诊疗依据。")

# 免构建内联单页：无任何外链（守门测试断言页面文本不含 http(s):// 与外链标签）
_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { --line:#d8dee6; --ink:#1c2733; --dim:#5b6b7b; --brand:#0b62a4;
          --ok:#1a7f37; --warn:#9a6700; --bad:#c1341b; --bg:#f5f7fa; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:"Microsoft YaHei","PingFang SC",sans-serif;
         color:var(--ink); background:var(--bg); }
  header { background:var(--brand); color:#fff; padding:18px 24px; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:6px 0 0; font-size:12px; opacity:.85; }
  main { max-width:960px; margin:0 auto; padding:20px 16px 48px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:8px;
          padding:16px 20px; margin-bottom:16px; }
  .card h2 { font-size:15px; margin:0 0 12px; color:var(--brand); }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
  input[type=file] { font-size:13px; }
  button { background:var(--brand); color:#fff; border:0; border-radius:6px;
           padding:8px 22px; font-size:14px; cursor:pointer; }
  button:disabled { background:#9bb8cc; cursor:default; }
  .meta { font-size:12px; color:var(--dim); margin-top:8px; }
  .badge { display:inline-block; border-radius:12px; padding:2px 12px;
           font-size:13px; color:#fff; }
  .badge.pass { background:var(--ok); } .badge.need_confirm { background:var(--warn); }
  .badge.fail { background:var(--bad); }
  .stat { display:inline-block; min-width:110px; background:var(--bg);
          border:1px solid var(--line); border-radius:6px; padding:8px 12px;
          margin:4px 6px 4px 0; font-size:13px; }
  .stat b { display:block; font-size:18px; margin-top:2px; }
  .finding { border:1px solid var(--line); border-left-width:4px; border-radius:6px;
             padding:10px 14px; margin:10px 0; font-size:13px; background:#fff; }
  .finding.f { border-left-color:var(--bad); }
  .finding.nc { border-left-color:var(--warn); }
  .finding .head { font-weight:bold; margin-bottom:4px; }
  .finding .sev { float:right; font-size:12px; border-radius:10px; padding:1px 10px; color:#fff; }
  .sev.CRITICAL { background:#8b1a1a; } .sev.HIGH { background:var(--bad); }
  .sev.MEDIUM { background:var(--warn); } .sev.LOW { background:var(--dim); }
  .sev.NEED_CONFIRM { background:#6e5494; }
  .kv { color:var(--dim); margin:3px 0; line-height:1.6; }
  .kv b { color:var(--ink); }
  .warn { color:var(--warn); font-size:12px; }
  .err { color:var(--bad); font-size:13px; }
  footer { text-align:center; font-size:12px; color:var(--dim); padding:16px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <p>上传出院病历部件（.txt）→ 自动解析、质控、分级统计；规则优先，LLM 仅兜底</p>
</header>
<main>
  <div class="card">
    <h2>1. 选择病历部件文件</h2>
    <div class="row">
      <input type="file" id="files" multiple accept=".txt">
      <button id="go">开始质控</button>
    </div>
    <p class="meta" id="env">加载环境中…</p>
    <p class="meta">部件按内容自动识别：入院记录 / 病程记录 / 手术记录 / 出院记录 / 医嘱单 / 检验报告，可多选、可缺部件。</p>
  </div>
  <div id="result"></div>
</main>
<footer>__DISCLAIMER__</footer>
<script>
"use strict";
var STATUS = {"pass":"通过","fail":"不通过","need_confirm":"待人工确认"};
var BADGE = {"pass":"pass","fail":"fail","need_confirm":"need_confirm"};
function esc(s){ var d=document.createElement("div"); d.textContent=s==null?"":String(s); return d.innerHTML; }
fetch("/api/status").then(function(r){return r.json();}).then(function(s){
  document.getElementById("env").textContent =
    "v" + s.version + " ｜ 知识库规则 " + s.n_rules + " 条 ｜ LLM 兜底：" +
    (s.llm_available ? "已配置" : "未配置（纯规则通路）");
}).catch(function(){ document.getElementById("env").textContent = "环境状态获取失败"; });
document.getElementById("go").onclick = function(){
  var input = document.getElementById("files");
  var box = document.getElementById("result");
  if (!input.files.length) { box.innerHTML = '<p class="err">请先选择至少一个 .txt 部件文件</p>'; return; }
  var btn = this; btn.disabled = true;
  box.innerHTML = '<p class="meta">质控中…</p>';
  var fd = new FormData();
  for (var i = 0; i < input.files.length; i++) fd.append("files", input.files[i], input.files[i].name);
  fetch("/api/check", {method:"POST", body: fd})
    .then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
    .then(function(res){
      btn.disabled = false;
      if (!res.ok || res.j.error) { box.innerHTML = '<p class="err">质控失败：' + esc(res.j.error || res.j.detail || "未知错误") + '</p>'; return; }
      box.innerHTML = render(res.j);
    })
    .catch(function(e){ btn.disabled = false; box.innerHTML = '<p class="err">请求失败：' + esc(e) + '</p>'; });
};
function render(j){
  var s = j.summary || {};
  var html = '<div class="card"><h2>2. 质控结论'
    + '　<span class="badge ' + BADGE[s.overall] + '">' + esc(s.overall_label) + '</span></h2>'
    + '<div>'
    + '<span class="stat">参评规则<b>' + esc(s.n_rules) + '</b></span>'
    + '<span class="stat">通过<b>' + esc(s.n_pass) + '</b></span>'
    + '<span class="stat">不通过<b>' + esc(s.n_fail) + '</b></span>'
    + '<span class="stat">待人工确认<b>' + esc(s.n_need_confirm) + '</b></span>'
    + '<span class="stat">依据关联率<b>' + (s.basis_linkage_rate * 100).toFixed(1) + '%</b></span>'
    + '</div>'
    + '<p class="meta">解析告警 ' + (j.parse_warnings ? j.parse_warnings.length : 0) + ' 条'
    + '；节点耗时 ' + Object.keys(j.timings || {}).map(function(k){ return k + " " + (j.timings[k]*1000).toFixed(0) + "ms"; }).join(" / ")
    + '</p></div>';
  (j.parse_warnings || []).forEach(function(w){
    html += '<p class="warn">解析告警：' + esc(w) + '</p>';
  });
  var list = (j.findings || []).filter(function(f){ return f.status !== "pass"; });
  html += '<div class="card"><h2>3. 非通过结论（' + list.length + ' 条）</h2>';
  if (!list.length) html += '<p class="meta">全部规则通过。</p>';
  list.forEach(function(f){
    html += '<div class="finding ' + (f.status === "fail" ? "f" : "nc") + '">'
      + '<span class="sev ' + esc(f.severity) + '">' + esc(f.severity_label) + '</span>'
      + '<div class="head">' + esc(f.rule_id) + " " + esc(f.rule_name)
      + '　<span class="badge ' + BADGE[f.status] + '">' + esc(STATUS[f.status] || f.status) + '</span></div>';
    if (f.basis) html += '<p class="kv"><b>依据</b>' + esc(f.basis.document + " " + f.basis.document_no + " " + f.basis.clause)
      + "（" + esc(f.basis.status) + "）｜条文摘录：「" + esc(f.basis.quote) + '」</p>';
    (f.evidence || []).forEach(function(ev){
      html += '<p class="kv"><b>病历证据</b>[' + esc(ev.part) + '] ' + esc(ev.quote) + '</p>';
    });
    if (f.suggestion) html += '<p class="kv"><b>整改建议</b>' + esc(f.suggestion) + '</p>';
    html += '</div>';
  });
  return html + '</div>';
}
</script>
</body>
</html>
""".replace("__TITLE__", _PAGE_TITLE).replace("__DISCLAIMER__", _DISCLAIMER)


def _import_fastapi():
    """惰性导入 fastapi；缺失时抛带安装提示的 ImportError。"""
    try:
        import fastapi  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Web 面板需要 web 组件：pip install 'mrqc[web]'（fastapi/uvicorn/python-multipart）"
        ) from exc


def web_available() -> bool:
    """web 依赖是否可用（CLI demo 展示用）。"""
    try:
        import fastapi  # noqa: F401
        return True
    except ImportError:
        return False


def create_app():
    """创建 FastAPI 应用：multipart 上传病历部件 → 质控结论展示。"""
    _import_fastapi()
    from typing import List

    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.responses import HTMLResponse, JSONResponse

    from ..knowledge import knowledge_status
    from ..llm import llm_available

    # /docs、/redoc、openapi 全部显式关闭：Swagger UI 引 CDN，破坏 0 外链纪律
    app = FastAPI(title=_PAGE_TITLE, version=__version__,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(_PAGE_HTML)

    @app.get("/api/status")
    def status():
        ks = knowledge_status()
        return {
            "version": __version__,
            "n_rules": ks["rules"],
            "n_blocks": ks["blocks"],
            "llm_available": llm_available(),
            "disclaimer": _DISCLAIMER,
        }

    @app.post("/api/check")
    async def check(files: List[UploadFile] = File(...)):
        # 部件按内容识别（detect_part），文件名仅作落盘；非 txt 内容走告警通路
        with tempfile.TemporaryDirectory(prefix="mrqc_web_") as tmp:
            for f in files:
                name = Path(f.filename or "upload.txt").name
                if not name.lower().endswith(".txt"):
                    name += ".txt"
                data = await f.read()
                (Path(tmp) / name).write_bytes(data)
            pipe = build_pipeline(tmp)
            ctx = pipe.run()
        if not pipe.success:
            raise HTTPException(status_code=500,
                                detail="质控流水线失败：%s"
                                       % "；".join(r.error for r in pipe.results if not r.ok))
        card = ctx[CTX_CARD]
        record_id = "web_%s" % datetime.now().strftime("%Y%m%d_%H%M%S")
        return JSONResponse({
            "record_id": record_id,
            "patient": card.patient.to_dict(),
            "findings": [f.to_dict() for f in ctx[CTX_FINDINGS]],
            "summary": ctx[CTX_SUMMARY],
            "parse_warnings": card.parse_warnings,
            "timings": ctx[CTX_TIMINGS],
            "disclaimer": _DISCLAIMER,
        })

    return app


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动 Web 面板（uvicorn；`py -m mrqc.web` 入口）。"""
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "Web 面板需要 web 组件：pip install 'mrqc[web]'（fastapi/uvicorn/python-multipart）"
        ) from exc
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
