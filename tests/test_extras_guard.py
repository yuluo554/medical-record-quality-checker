"""extras 守门测试：依赖分层声明必须覆盖运行期与测试期真实 import。

背景（姊妹项目实测教训）：
- FastAPI UploadFile 需要 python-multipart，漏声明时 uvicorn 启动即崩；
- 测试期依赖缺失会让整模块静默跳过（dev 绿但悄悄少跑）。
本测试静态锁定 pyproject extras 声明与 CI 安装范围。
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _extras_section() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"\[project\.optional-dependencies\](.*?)(?=\n\[|\Z)", text, re.S)
    assert m, "pyproject.toml 缺少 [project.optional-dependencies] 节"
    return m.group(1)


def _extra_block(section: str, name: str) -> str:
    m = re.search(r"^%s\s*=\s*\[(.*?)\]" % name, section, re.S | re.M)
    assert m, "extras 缺少 %s 组" % name
    return m.group(1)


def test_web_extra_declares_python_multipart():
    web = _extra_block(_extras_section(), "web")
    assert "python-multipart" in web, "web extra 必须声明 python-multipart（UploadFile 运行期依赖）"
    for pkg in ("fastapi", "uvicorn"):
        assert pkg in web


def test_report_and_dev_extras_declared():
    section = _extras_section()
    assert "python-docx" in _extra_block(section, "report")
    assert "pytest" in _extra_block(section, "dev")


def test_lazy_import_guards_present():
    """report/web 必须带惰性导入守卫（缺依赖给安装提示，exit 2 不崩）。"""
    web_init = (ROOT / "src" / "mrqc" / "web" / "__init__.py").read_text(encoding="utf-8")
    assert "_import_fastapi" in web_init and "pip install" in web_init
    report_init = (ROOT / "src" / "mrqc" / "report" / "__init__.py").read_text(encoding="utf-8")
    assert "_import_docx" in report_init and "pip install" in report_init


def test_ci_installs_all_extras():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert '.[dev,web,report]"' in ci, "CI 必须显式安装全量 extras（防静默少跑）"
    assert '"3.8"' in ci, "CI 必须覆盖 Python 3.8 底线（requires-python 对齐）"


def _src_py_files():
    return sorted((ROOT / "src" / "mrqc").rglob("*.py"))


def test_runtime_third_party_imports_confined_to_extras_packages():
    """M5：report/web 运行期 import 必须收敛在各自包内（惰性守卫唯一入口）。

    docx 只允许出现在 mrqc/report/；fastapi/uvicorn 只允许出现在 mrqc/web/。
    其他模块（含 CLI/编排层）一律经由 mrqc.report / mrqc.web 的可用性探针，
    防止第三方运行期 import 逃逸到核心通路（核心通路零第三方依赖纪律）。
    """
    confined = {
        ("import docx", "from docx"): "report",
        ("import fastapi", "from fastapi", "import uvicorn", "from uvicorn"): "web",
    }
    for path in _src_py_files():
        rel = path.relative_to(ROOT / "src" / "mrqc").as_posix()
        text = path.read_text(encoding="utf-8")
        for patterns, package in confined.items():
            hit = any(re.search(r"^\s*%s\b" % re.escape(p), text, re.M) for p in patterns)
            if hit:
                assert rel.startswith(package + "/") or rel == package + "__init__.py", \
                    "第三方运行期 import 逃逸：%s 引用了 %s extra 的包" % (rel, package)


def test_web_page_no_external_links():
    """Web 单页 0 外链（断网可演示）：内联页文本禁含外链引用。"""
    from mrqc.web import _PAGE_HTML

    assert "http://" not in _PAGE_HTML and "https://" not in _PAGE_HTML
    for banned in ("<link", "script src", "@import"):
        assert banned not in _PAGE_HTML
