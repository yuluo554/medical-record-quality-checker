"""支持 `py -m mrqc.web` 直接启动 Web 面板（Windows 下控制台脚本可能不在 PATH）。

用法：py -X utf8 -m mrqc.web [--host 127.0.0.1] [--port 8000]
"""

import argparse
import sys

from . import serve


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="mrqc.web", description="mrqc Web 面板（FastAPI 单页，0 外链断网可演示）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    args = parser.parse_args(argv)
    try:
        serve(args.host, args.port)
    except ImportError as exc:
        print("[缺依赖] %s" % exc, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
