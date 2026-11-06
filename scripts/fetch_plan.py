#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""兼容入口 —— 取数计划已并入 update.py。

    python scripts/fetch_plan.py            # 等价于 update.py plan
    python scripts/fetch_plan.py --months 12

保留这个文件只为不打断旧习惯 / 旧文档引用。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    sys.exit(subprocess.run([sys.executable, os.path.join(HERE, "update.py"), "plan"]
                            + sys.argv[1:]).returncode)
