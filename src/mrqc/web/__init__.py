"""Web 面板层（FastAPI 免构建单页）。依赖属可选 extra，惰性导入。"""


def _import_fastapi():
    """惰性导入 fastapi；缺失时抛带安装提示的 ImportError。"""
    try:
        import fastapi  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Web 面板需要 web 组件：pip install 'mrqc[web]'（fastapi/uvicorn/python-multipart）"
        ) from exc


def create_app():
    """创建 FastAPI 应用：上传病历部件 → 参数卡 → 质控结论 → 报告预览。

    M5 实现（plan/05 里程碑 M5）。硬性要求：
    - 页面 0 外链（内联 CSS/JS），断网可演示；
    - /docs、/redoc 显式关闭（Swagger UI 引 CDN，破坏 0 外链）；
    - 上传走 multipart（python-multipart 是运行期必需依赖）。
    """
    _import_fastapi()
    raise NotImplementedError("Web 面板在 M5 实现（plan/05 里程碑 M5）")
