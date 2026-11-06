#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""环境自检：文件齐不齐、库对不对、待补表什么状态、运行时能不能出图。

    python scripts/check_env.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import config as C      # noqa: E402
import history as H     # noqa: E402

ok = True


def line(name, value, good, hint=""):
    global ok
    flag = "OK  " if good else "FAIL"
    if not good:
        ok = False
    print("[%s] %-14s %s" % (flag, name, value))
    if not good and hint:
        print("       → " + hint)


def main():
    print("=" * 66)
    print("环境自检 · 公司回购与大股东减仓监控（望京博格版）")
    print("=" * 66)

    build_py = os.path.join(HERE, "build.py")
    update_py = os.path.join(HERE, "update.py")
    for p in (C.DATA, C.TPL, build_py, update_py):
        line("文件 " + os.path.basename(p), p, os.path.exists(p),
             "skill 目录不完整，重新解压安装")
    if not os.path.exists(C.DATA):
        return 1

    obj = H.load()
    rows = obj["months"]
    line("月份数", len(rows), len(rows) >= 12, "至少 12 个月才够画趋势")
    if not rows:
        return 1
    print("       区间 %s ~ %s" % (rows[0]["m"], rows[-1]["m"]))
    print("       更新 %s" % obj.get("updated", "—"))

    probs = H.verify(obj)
    fails = [p for p, lv in probs if lv == "fail"]
    warns = [p for p, lv in probs if lv == "warn"]
    line("库结构", "通过" if not fails else "；".join(fails), not fails,
         "断月/越界/锚点不符，用 history.py 逐条修")
    for w in warns:
        print("       提醒 %s" % w)

    n_bak = len(os.listdir(C.BACKUP_DIR)) if os.path.isdir(C.BACKUP_DIR) else 0
    print("       自动备份 %d 份  %s" % (n_bak, C.BACKUP_DIR))

    if os.path.exists(C.PENDING):
        with open(C.PENDING, encoding="utf-8") as f:
            pend = json.load(f)
        done = sum(1 for r in pend.get("months", []) if r.get("done"))
        print("       待补表 %d 行（已完成 %d）  %s"
              % (len(pend.get("months", [])), done, C.PENDING))
    else:
        print("       待补表 未生成（update.py plan 时创建）")

    tb = sum(r["buyback"] for r in rows)
    tr = sum(r["reduce"] for r in rows)
    print("       累计回购 %.1f 亿 | 累计减仓 %.1f 亿 | 覆盖 %.1f%%"
          % (tb, tr, tb / tr * 100 if tr else 0))

    try:
        import runtime
        node, mods, chrome = runtime.find_node(), runtime.find_node_modules(), runtime.find_chrome()
        line("node", node or "未找到", bool(node), runtime.NODE_HINT)
        line("playwright", mods or "未找到", bool(mods), runtime.NODE_MODULES_HINT)
        line("浏览器", chrome or "未找到", bool(chrome), runtime.CHROME_HINT)
        print("       一条命令出报告：python scripts/update.py build")
    except Exception as e:
        line("运行时探测", "失败：%s" % e, False, "手动确认 node 与 Chrome")

    print("-" * 66)
    print("MCP 这条人工确认：问一句「2026年10月A股全部上市公司股份回购实际金额合计，单位亿元」，")
    print("回 221.95 亿（数值 22,194,878,014）才算通。不通报「没找到数据」或量级差 1 万倍。")
    print("=" * 66)
    print("自检结论：%s" % ("通过" if ok else "有问题，按上面 FAIL 逐条处理"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
