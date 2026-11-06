#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""增量更新的总入口：算缺口 → 取数 → 入库 → 出报告。

    python scripts/update.py status          # 一眼看：库到哪、缺几个月、下一步做什么
    python scripts/update.py plan            # 算缺口，写 data/pending.json，打印可直接发的问句
    python scripts/update.py fill 2026-11 --buy 120.5 --red 300.2 --hs300 4021.7
    python scripts/update.py fill --from 值.json
    python scripts/update.py apply           # 手改完 data/pending.json 后批量入库
    python scripts/update.py build           # 出 HTML + 长图（不联网）
    python scripts/update.py all             # apply + build

设计原则：
  · 历史数据是资产，只增不改：库文件里的旧月份永不重取
  · 取到一个月就落一个月（fill），中断不丢进度
  · 沪深300 缺口区间一次取完，不做逐月调用
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import config as C      # noqa: E402
import history as H     # noqa: E402

PY = sys.executable


# ---------------------------------------------------------------- pending
def load_pending():
    if not os.path.exists(C.PENDING):
        return {"created": "", "asof": "", "months": []}
    with open(C.PENDING, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pending(obj):
    os.makedirs(os.path.dirname(C.PENDING), exist_ok=True)
    tmp = C.PENDING + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, C.PENDING)


def row_template(key):
    d = C.last_day(*C.key_to_pair(key))
    return {"m": key, "buyback": None, "reduce": None, "hs300": None, "done": False,
            "q_buyback": C.q_buy(d), "q_reduce": C.q_red(d)}


def eff_asof(obj, asof=None):
    """本次比较用的截止月：用户指定 > 库尾月 > 上一个完整月，取最晚的那个。

    否则刚补完的新月份会被当成「还没到」，缺口报告永远是错的。
    """
    cand = [asof or C.default_asof()]
    if obj["months"]:
        cand.append(obj["months"][-1]["m"])
    return max(cand)


def fill_state(row):
    n = sum(1 for k in C.FIELDS if row.get(k) not in (None, ""))
    return n


# ---------------------------------------------------------------- 缺口
def compute_gap(obj, asof, months):
    have = {r["m"] for r in obj["months"]}
    window = C.month_seq(C.month_key(*C.shift_month(*C.key_to_pair(asof), months - 1)), asof)
    return window, [m for m in window if m not in have]


def cmd_plan(obj, asof, months):
    asof = eff_asof(obj, asof)
    window, missing = compute_gap(obj, asof, months)
    pend = load_pending()
    known = {r["m"]: r for r in pend.get("months", [])}

    rows = []
    for m in missing:
        r = known.get(m) or row_template(m)
        r.setdefault("done", False)
        r.setdefault("q_buyback", row_template(m)["q_buyback"])
        r.setdefault("q_reduce", row_template(m)["q_reduce"])
        rows.append(r)
    pend = {"created": dt.datetime.now().replace(microsecond=0).isoformat(timespec="minutes"),
            "asof": asof, "months": rows}
    save_pending(pend)

    print("库内 %d 个月  %s ~ %s"
          % (len(obj["months"]), obj["months"][0]["m"], obj["months"][-1]["m"]))
    print("窗口 %d 个月  %s ~ %s" % (len(window), window[0], window[-1]))
    if not missing:
        print("缺口 无。直接 python scripts/update.py build 出报告。")
        return 0

    print("缺口 %d 个月：%s" % (len(missing), "、".join(missing)))
    print("需发起 %d 次调用（回购 %d + 减仓 %d + 沪深300 1）"
          % (len(missing) * 2 + 1, len(missing), len(missing)))
    print("-" * 76)

    b, e = C.key_to_pair(missing[0]), C.key_to_pair(missing[-1])
    bd = dt.date(b[0], b[1], 1)
    ed = C.last_day(*e)
    print("沪深300 月末收盘（区间一次取完，不要逐月问）：")
    print('  get_index_kline(windcode="000300.SH", begin_date="%s", end_date="%s", period="12")'
          % (bd.isoformat(), ed.isoformat()))
    print("  取 MATCH 列（月收盘），按月对齐。")
    print("-" * 76)

    for i, m in enumerate(missing, 1):
        r = known.get(m, row_template(m))
        print("[%d/%d] %s" % (i, len(missing), m))
        print("  回购  " + r["q_buyback"])
        print("  减仓  " + r["q_reduce"])
    print("-" * 76)
    print("取到即入库，单月一条，中断不丢：")
    print("  python scripts/update.py fill %s --buy <回购> --red <减仓> --hs300 <月末收盘>"
          % missing[0])
    print("待补表已写到 %s（也可手改后 apply）" % C.PENDING)
    print("节奏：一轮消息最多 2 条，3 条必挂中间那条（QPS≈2）。")
    return 0


# ---------------------------------------------------------------- 入库
def _merge_and_report(obj, items, force):
    rep = H.merge(obj, items, force=force)
    for r in rep["new"]:
        print("新增 %s  buy %7.2f / red %8.2f / hs300 %8.2f"
              % (r["m"], r["buyback"], r["reduce"], r["hs300"]))
    for prev, rec, diff in rep["updated"]:
        print("覆盖 %s  %s" % (rec["m"], H.fmt(rec)))
        for k, (a, b) in diff.items():
            print("      %s %.2f → %.2f" % (C.LABEL[k], a, b))
    for r in rep["same"]:
        print("跳过 %s  与原值一致" % r["m"])
    for prev, rec, diff in rep["blocked"]:
        print("拒写 %s  库里是 %.2f/%.2f/%.2f，新值不同："
              % (rec["m"], prev["buyback"], prev["reduce"], prev["hs300"]))
        for k, (a, b) in diff.items():
            print("      %s %.2f → %.2f" % (C.LABEL[k], a, b))
        print("      确认要改（Wind 修订）加 --force 重跑")
    for e in rep["errors"]:
        print("[FAIL] " + e)
    return rep


def cmd_fill(obj, asof, months, key, buy, red, hs300, path, force):
    if path:
        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)
        if "buyback" in items:
            sys.exit("平铺 JSON 需要 --m，或改成 {\"2026-11\": {...}} 形态")
    elif key:
        items = {key: {"buyback": buy, "reduce": red, "hs300": hs300}}
    else:
        sys.exit("要么给月份（--m 用位置参数 2026-11），要么给 --from 值.json")

    bad = [m for m in items if m > C.default_asof()]
    if bad:
        print("[WARN] %s 还没走完，取到的是不完整月份，入库会让趋势末端失真" % "、".join(bad))

    before = len(obj["months"])
    rep = _merge_and_report(obj, items, force)
    added = len(obj["months"]) - before

    if added:
        pend = load_pending()
        got = {r["m"] for r in obj["months"]}
        # 已入库的行直接从待补表移除，表里只留真正还欠的
        pend["months"] = [r for r in pend.get("months", []) if r["m"] not in got]
        save_pending(pend)

    print("—— 库内 %d 个月，最后 %s" % (len(obj["months"]), obj["months"][-1]["m"]))
    probs = [p for p, lv in H.verify(obj) if lv == "fail"]
    for p in probs:
        print("[FAIL] " + p)
    probe = max([x for x in [asof] + list(items) if x])
    nxt = fill_remaining(obj, probe, months)
    if nxt:
        print("还差 %d 个月：%s" % (len(nxt), "、".join(nxt)))
        print("下一步  python scripts/update.py fill %s --buy <回购> --red <减仓> --hs300 <收盘>"
              % nxt[0])
    else:
        print("缺口已补齐 → python scripts/update.py build")
    return 0 if not (rep["errors"] or rep["blocked"]) else 1


def cmd_apply(obj, asof, months, force):
    asof = eff_asof(obj, asof)
    pend = load_pending()
    rows = pend.get("months", [])
    if not rows:
        print("待补表是空的。先 python scripts/update.py plan")
        return 0
    ready = {r["m"]: r for r in rows
             if not r.get("done") and fill_state(r) == len(C.FIELDS)}
    todo = [r for r in rows if not r.get("done") and fill_state(r) < len(C.FIELDS)]
    if not ready:
        print("没有可提交的行（%d 行还没填全）。" % len(todo))
        for r in todo:
            print("  %s  已填 %d/%d" % (r["m"], fill_state(r), len(C.FIELDS)))
        return 0

    rep = _merge_and_report(obj, ready, force)
    got = {r["m"] for r in obj["months"]}
    kept = [r for r in rows if r["m"] not in got and r["m"] not in ready]
    pend["months"] = kept
    pend["asof"] = asof or pend.get("asof", "")
    save_pending(pend)
    print("—— 入库 %d 个月，待补表剩 %d 行" % (len(ready), len(kept)))
    return 0 if not (rep["errors"] or rep["blocked"]) else 1


def fill_remaining(obj, asof, months):
    _w, missing = compute_gap(H.load(), eff_asof(obj, asof), months)
    return missing


# ---------------------------------------------------------------- 出报告
def cmd_build(obj, months, png):
    asof = eff_asof(obj)
    _w, missing = compute_gap(obj, asof, months)
    probs = H.verify(obj)
    for p, lv in probs:
        print("%s %s" % ("[FAIL]" if lv == "fail" else "[WARN]", p))
    if missing:
        print("[WARN] 还缺 %d 个月：%s（报告会以 %s 收尾）"
              % (len(missing), "、".join(missing), obj["months"][-1]["m"]))

    r = subprocess.run([PY, os.path.join(HERE, "build.py"), "--out", C.OUT_DIR],
                       cwd=ROOT)
    if r.returncode != 0:
        return r.returncode
    name = "公司回购与大股东减仓监控_%s" % dt.date.today().strftime("%Y%m%d")
    html = os.path.join(C.OUT_DIR, name + ".html")
    if not png:
        print("HTML  %s" % html)
        return 0
    node = _node()
    if not node:
        print("[WARN] 没找到 node，跳过长图。HTML 照常可用：%s" % html)
        return 0
    p = subprocess.run([node, os.path.join(HERE, "export_long.js"),
                        html, os.path.join(C.OUT_DIR, name + ".png"), "1180", "2360"],
                       cwd=ROOT)
    if p.returncode == 0:
        print("PNG   %s" % os.path.join(C.OUT_DIR, name + ".png"))
    return 0


def _node():
    import shutil
    return shutil.which("node")


# ---------------------------------------------------------------- 概况
def cmd_status(obj, asof, months):
    asof = eff_asof(obj, asof)
    _w, missing = compute_gap(obj, asof, months)
    rows = obj["months"]
    print("库     %d 个月  %s ~ %s  更新 %s"
          % (len(rows), rows[0]["m"], rows[-1]["m"], obj.get("updated", "—")))
    print("窗口   %d 个月  截至 %s" % (months, asof))
    probs = H.verify(obj)
    fails = [p for p, lv in probs if lv == "fail"]
    warns = [p for p, lv in probs if lv == "warn"]
    print("校验   %s" % ("通过" if not fails else "；".join(fails)))
    for w in warns:
        print("       提醒：%s" % w)
    if not missing:
        print("缺口   无")
        print("下一步 python scripts/update.py build")
        return 0

    pend = load_pending()
    pmap = {r["m"]: r for r in pend.get("months", [])}
    ready = [m for m in missing if m in pmap and fill_state(pmap[m]) == len(C.FIELDS)]
    print("缺口   %d 个月：%s（需 %d 次调用）"
          % (len(missing), "、".join(missing), len(missing) * 2 + 1))
    print("待补   %d/%d 已填%s" % (len(ready), len(missing),
                                 "" if ready else "  → data/pending.json 是空表"))
    if ready:
        print("下一步 python scripts/update.py apply")
    else:
        print("下一步 python scripts/update.py plan     # 打印问句")
        print("       python scripts/update.py fill %s --buy X --red Y --hs300 Z" % missing[0])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?",
                    choices=["status", "plan", "fill", "apply", "build", "all"],
                    default="status")
    ap.add_argument("m", nargs="?", help="fill 用：2026-11")
    ap.add_argument("--asof", default=None, help="截止月，默认上一个完整月")
    ap.add_argument("--months", type=int, default=60)
    ap.add_argument("--from", dest="path", default=None, help="fill 用：批量值 JSON")
    ap.add_argument("--buy", type=float)
    ap.add_argument("--red", type=float)
    ap.add_argument("--hs300", type=float)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-png", action="store_true")
    a = ap.parse_args()

    obj = H.load()
    asof = a.asof or C.default_asof()

    if a.cmd == "status":
        return cmd_status(obj, a.asof, a.months)
    if a.cmd == "plan":
        return cmd_plan(obj, asof, a.months)
    if a.cmd == "fill":
        if a.path is None and a.m and a.m.upper().endswith(".JSON"):
            a.path, a.m = a.m, None
        return cmd_fill(obj, asof, a.months, a.m, a.buy, a.red, a.hs300, a.path, a.force)
    if a.cmd == "apply":
        return cmd_apply(obj, asof, a.months, a.force)
    if a.cmd == "build":
        return cmd_build(obj, a.months, not a.no_png)
    if a.cmd == "all":
        rc = cmd_apply(obj, asof, a.months, a.force)
        if rc == 0:
            rc = cmd_build(obj, a.months, not a.no_png)
        return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
