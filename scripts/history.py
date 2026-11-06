#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""月度库：读写、校验、备份、审计。

    python scripts/history.py stat                 # 概况 + 断点 + 越界
    python scripts/history.py verify               # 严格校验，非 0 退出
    python scripts/history.py add --m 2026-11 --buy 120.5 --red 300.2 --hs300 4021.7
    python scripts/history.py add 值.json          # {"2026-11": {...}, ...}
    python scripts/history.py del 2026-11
    python scripts/history.py print 2026
    python scripts/history.py csv                  # 导出 CSV 到 stdout

写入规则：
  · 原子写（临时文件 + os.replace），中断不会留下半截文件
  · 每次写入前自动备份到 data/backups/，保留最近 20 份
  · 同月数值有变化默认拒写并提示差异，确认无误加 --force 覆盖
  · 每次变更追加一行到 data/fetch-log.jsonl
  · 缺字段 / 越界 / 非数字一律拒收，宁可缺月不写假 0
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config as C  # noqa: E402


# ---------------------------------------------------------------- 底层
def load():
    if not os.path.exists(C.DATA):
        return {"updated": "", "unit": "亿元", "months": []}
    with open(C.DATA, "r", encoding="utf-8") as f:
        obj = json.load(f)
    obj.setdefault("months", [])
    obj["months"].sort(key=lambda r: r["m"])
    return obj


def backup(obj):
    os.makedirs(C.BACKUP_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(C.BACKUP_DIR, "history-%s.json" % stamp)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    olds = sorted(os.listdir(C.BACKUP_DIR))
    for name in olds[:-C.BACKUP_KEEP]:
        try:
            os.remove(os.path.join(C.BACKUP_DIR, name))
        except OSError:
            pass
    return dst


def save(obj, updated=None, keep_backup=True):
    obj["months"].sort(key=lambda r: r["m"])
    obj["updated"] = updated or dt.date.today().isoformat()
    bpath = backup(obj) if keep_backup else None
    tmp = C.DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, C.DATA)
    return bpath


def log(act, rec, prev=None, note=""):
    line = {"ts": dt.datetime.now().replace(microsecond=0).isoformat(),
            "act": act, "m": rec["m"],
            "buyback": rec["buyback"], "reduce": rec["reduce"], "hs300": rec["hs300"]}
    if prev:
        line["prev"] = {k: prev[k] for k in C.FIELDS}
    if note:
        line["note"] = note
    with open(C.LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 校验
def check_record(m, rec):
    """单条校验，返回问题列表（空 = 通过）。"""
    errs = []
    if len(m) != 7 or m[4] != "-" or not m[:4].isdigit() or not m[5:].isdigit():
        errs.append("月份格式应为 YYYY-MM，实际 %r" % m)
        return errs
    if not (1 <= int(m[5:]) <= 12):
        errs.append("%s 月份取值非法" % m)
    for k in C.FIELDS:
        v = rec.get(k)
        if v is None:
            errs.append("%s 缺 %s，拒绝写入（宁可缺月，也不要假 0）" % (m, C.LABEL[k]))
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            errs.append("%s 的 %s 不是数字：%r" % (m, C.LABEL[k], rec.get(k)))
            continue
        lo, hi = C.RANGES[k]
        if not (lo <= v <= hi):
            errs.append("%s 的 %s=%.2f 越界（合理 %.0f~%.0f），多半是单位错了"
                        % (m, C.LABEL[k], v, lo, hi))
    return errs


def normalize(rec):
    return {"m": rec["m"], **{k: round(float(rec[k]), 2) for k in C.FIELDS}}


def gaps(rows):
    out = []
    for i in range(1, len(rows)):
        y0, m0 = C.key_to_pair(rows[i - 1]["m"])
        y1, m1 = C.key_to_pair(rows[i]["m"])
        if (y1 * 12 + m1) - (y0 * 12 + m0) != 1:
            out.append((rows[i - 1]["m"], rows[i]["m"]))
    return out


def verify(obj, strict=True):
    """返回 (problems, level) 列表；level: fail / warn。"""
    rows = obj["months"]
    out = []
    if not rows:
        return [("库是空的", "fail")]

    keys = [r["m"] for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        out.append(("重复月份：%s" % "、".join(dup), "fail"))
    for r in rows:
        for e in check_record(r["m"], r):
            out.append((e, "fail"))
    for a, b in gaps(rows):
        out.append(("断月：%s → %s 之间缺月" % (a, b), "fail"))

    idx = {r["m"]: r for r in rows}
    for m, kv in C.ANCHORS.items():
        if m not in idx:
            continue
        for k, want in kv.items():
            got = idx[m][k]
            if abs(got - want) > max(0.02 * abs(want), 0.5):
                out.append(("%s %s 锚点应为 %.2f，实为 %.2f" % (m, C.LABEL[k], want, got), "fail"))

    # 尾部新鲜度：库的最后一个月落后于今天该有的月份，只是提醒，不算错
    want_tail = C.default_asof()
    if rows[-1]["m"] < want_tail:
        out.append(("数据截止 %s，%s 还没入库" % (rows[-1]["m"], want_tail), "warn"))
    return out


# ---------------------------------------------------------------- 写入
def merge(obj, items, force=False, dry=False, note=""):
    """把 {月份: {buyback,reduce,hs300}} 合进库。返回报告 dict。"""
    idx = {r["m"]: i for i, r in enumerate(obj["months"])}
    rep = {"new": [], "updated": [], "same": [], "blocked": [], "errors": []}

    for m in sorted(items):
        raw = items[m]
        errs = check_record(m, raw)
        if errs:
            rep["errors"].extend(errs)
            continue
        rec = normalize({"m": m, **raw})
        if m not in idx:
            rep["new"].append(rec)
            if not dry:
                obj["months"].append(rec)
        else:
            prev = obj["months"][idx[m]]
            diff = {k: (prev[k], rec[k]) for k in C.FIELDS if abs(prev[k] - rec[k]) > 0.005}
            if not diff:
                rep["same"].append(rec)
            elif force:
                rep["updated"].append((prev, rec, diff))
                if not dry:
                    obj["months"][idx[m]] = rec
            else:
                rep["blocked"].append((prev, rec, diff))

    if not dry and (rep["new"] or rep["updated"]):
        save(obj)
        for r in rep["new"]:
            log("add", r, note=note or "新增")
        for prev, rec, _d in rep["updated"]:
            log("update", rec, prev=prev, note=note or "覆盖（--force）")
    return rep


def drop(obj, m):
    before = len(obj["months"])
    obj["months"] = [r for r in obj["months"] if r["m"] != m]
    if len(obj["months"]) == before:
        return False
    save(obj)
    log("del", {"m": m, "buyback": 0, "reduce": 0, "hs300": 0}, note="删除")
    return True


# ---------------------------------------------------------------- CLI
def fmt(rec):
    return "buy %7.2f / red %8.2f / hs300 %8.2f" % (rec["buyback"], rec["reduce"], rec["hs300"])


def cmd_stat(obj):
    rows = obj["months"]
    if not rows:
        print("库是空的。先 python scripts/update.py plan 看缺哪些月。")
        return 0
    tb = sum(r["buyback"] for r in rows)
    tr = sum(r["reduce"] for r in rows)
    print("文件      %s" % C.DATA)
    print("更新日期  %s" % obj.get("updated", "—"))
    print("月份数    %d" % len(rows))
    print("区间      %s ~ %s" % (rows[0]["m"], rows[-1]["m"]))
    print("累计回购  %.1f 亿（月均 %.1f）" % (tb, tb / len(rows)))
    print("累计减仓  %.1f 亿（月均 %.1f）" % (tr, tr / len(rows)))
    print("覆盖率    %.1f%%" % (tb / tr * 100 if tr else 0))
    g = gaps(rows)
    print("断点      %s" % ("无" if not g else "、".join("%s→%s" % x for x in g)))
    for p, lv in verify(obj):
        print("%s %s" % ("!!" if lv == "fail" else "…", p))
    n_log = 0
    if os.path.exists(C.LOG):
        with open(C.LOG, encoding="utf-8") as f:
            n_log = sum(1 for _ in f)
    print("审计流水  %s（%d 条）" % (C.LOG, n_log))
    return 0


def cmd_verify(obj):
    probs = verify(obj)
    fails = [p for p, lv in probs if lv == "fail"]
    warns = [p for p, lv in probs if lv == "warn"]
    for p in fails:
        print("[FAIL] " + p)
    for p in warns:
        print("[WARN] " + p)
    if not fails and not warns:
        print("[OK] %d 个月，无断点，量级与锚点全部通过" % len(obj["months"]))
    return 1 if fails else 0


def cmd_print(obj, year):
    rows = [r for r in obj["months"] if not year or r["m"].startswith(year)]
    print("月份     回购     减仓     沪深300    净额")
    for r in rows:
        print("%s  %7.2f  %8.2f  %8.2f  %8.2f"
              % (r["m"], r["buyback"], r["reduce"], r["hs300"], r["buyback"] - r["reduce"]))
    return 0


def cmd_csv(obj):
    print("month,buyback,reduce,hs300")
    for r in obj["months"]:
        print("%s,%.2f,%.2f,%.2f" % (r["m"], r["buyback"], r["reduce"], r["hs300"]))
    return 0


def cmd_add(obj, path, m, buy, red, hs300, force, note):
    items = {}
    if path:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if "buyback" in raw:
            if not m:
                sys.exit("平铺 JSON 需要 --m 2026-11")
            items[m] = raw
        else:
            items = raw
    elif m:
        items[m] = {"buyback": buy, "reduce": red, "hs300": hs300}
    else:
        sys.exit("要么给 JSON 路径，要么给 --m")

    rep = merge(obj, items, force=force, note=note)
    for r in rep["new"]:
        print("新增 %s  %s" % (r["m"], fmt(r)))
    for prev, rec, diff in rep["updated"]:
        print("覆盖 %s  %s" % (rec["m"], fmt(rec)))
        for k, (a, b) in diff.items():
            print("      %s %.2f → %.2f" % (C.LABEL[k], a, b))
    for r in rep["same"]:
        print("跳过 %s  与原值一致" % r["m"])
    for prev, rec, diff in rep["blocked"]:
        print("拒写 %s  已有 %.2f/%.2f/%.2f，新值不同："
              % (rec["m"], prev["buyback"], prev["reduce"], prev["hs300"]))
        for k, (a, b) in diff.items():
            print("      %s %.2f → %.2f" % (C.LABEL[k], a, b))
        print("      确认要改就加 --force 重跑")
    for e in rep["errors"]:
        print("[FAIL] " + e)
    print("—— 库内 %d 个月，最后 %s" % (len(obj["months"]), obj["months"][-1]["m"]))
    return 1 if (rep["errors"] or rep["blocked"]) else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("stat")
    sub.add_parser("verify")
    a = sub.add_parser("add")
    a.add_argument("json", nargs="?", default=None)
    a.add_argument("--m")
    a.add_argument("--buy", type=float)
    a.add_argument("--red", type=float)
    a.add_argument("--hs300", type=float)
    a.add_argument("--force", action="store_true", help="同月数值不同也覆盖")
    a.add_argument("--note", default="")
    d = sub.add_parser("del")
    d.add_argument("m")
    p = sub.add_parser("print")
    p.add_argument("year", nargs="?", default="")
    sub.add_parser("csv")
    args = ap.parse_args()

    obj = load()
    if args.cmd == "stat":
        return cmd_stat(obj)
    if args.cmd == "verify":
        return cmd_verify(obj)
    if args.cmd == "add":
        return cmd_add(obj, args.json, args.m, args.buy, args.red, args.hs300,
                       args.force, args.note)
    if args.cmd == "del":
        print("已删除 %s" % args.m if drop(obj, args.m) else "没有 %s" % args.m)
        return 0
    if args.cmd == "print":
        return cmd_print(obj, args.year)
    if args.cmd == "csv":
        return cmd_csv(obj)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
