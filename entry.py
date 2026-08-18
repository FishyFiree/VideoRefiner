"""PyInstaller 入口：以顶层脚本方式启动 GUI。

（gui.py 内部使用包内相对导入，直接作为 PyInstaller 入口脚本会报
"attempted relative import with no known parent package"；
本入口用绝对导入从包里调用 main，规避该问题。）
"""

import sys

from videorefiner.gui import main

sys.exit(main())
