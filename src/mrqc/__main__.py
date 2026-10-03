"""支持 `py -m mrqc` 直接调用（Windows 下 mrqc.exe 可能不在 PATH）。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
