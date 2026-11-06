#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""共享配置与月份工具。history / fetch_plan / update / check_env 都从这里取。

环境变量 WB_HISTORY_DATA 可指向另一个库文件，便于测试时不碰真库。
"""
import datetime as dt
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DATA_DIR = os.path.join(ROOT, "data")
DATA = os.environ.get("WB_HISTORY_DATA") or os.path.join(
    DATA_DIR, "buyback-reduction-history.json")
PENDING = os.path.join(DATA_DIR, "pending.json")
LOG = os.path.join(DATA_DIR, "fetch-log.jsonl")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

TPL = os.path.join(ROOT, "assets", "page_template.html")
OUT_DIR = os.path.join(ROOT, "output")

FIELDS = ("buyback", "reduce", "hs300")
LABEL = {"buyback": "回购", "reduce": "减仓", "hs300": "沪深300"}

# 量级闸门（亿元）：越界一律拒收，别让单位错误进库
RANGES = {
    "buyback": (1.0, 800.0),
    "reduce": (10.0, 1500.0),
    "hs300": (1500.0, 8000.0),
}

# 回归锚点：任一不符，先怀疑口径或换算，别改代码
ANCHORS = {
    "2024-02": {"buyback": 261.67, "reduce": 42.70},   # 回购五年峰值 / 减仓五年谷底
    "2026-10": {"buyback": 221.95, "reduce": 136.24},  # 窗口最后一个月
    "2023-09": {"reduce": 168.55},                     # 减持新规次月
}

BACKUP_KEEP = 20


# ---------------------------------------------------------------- 月份
def shift_month(y, m, back):
    total = y * 12 + (m - 1) - back
    return total // 12, total % 12 + 1


def last_day(y, m):
    nxt = dt.date(y + (m == 12), (m % 12) + 1, 1)
    return nxt - dt.timedelta(days=1)


def month_key(y, m):
    return "%04d-%02d" % (y, m)


def key_to_pair(key):
    return int(key[:4]), int(key[5:7])


def month_seq(first, last):
    """含首尾的月份序列，如 ('2021-11','2026-10') → ['2021-11', ...]"""
    y0, m0 = key_to_pair(first)
    y1, m1 = key_to_pair(last)
    n = (y1 * 12 + m1) - (y0 * 12 + m0)
    return [month_key(*shift_month(y0, m0, -k)) for k in range(n + 1)]


def default_asof(today=None):
    """默认截止月 = 上一个完整月。

    库里的每个月都必须是「整月实际发生额」，当月没走完就取数会得到一个残缺值，
    一旦入库，末端那根柱子永远是错的。所以默认永远退到上月。
    """
    today = today or dt.date.today()
    return month_key(*shift_month(today.year, today.month, 1))


def q_buy(d):
    return ("%d年%d月1日至%d年%d月%d日，A股全部上市公司股份回购实际金额合计，单位亿元"
            % (d.year, d.month, d.year, d.month, d.day))


def q_red(d):
    return ("%d年%d月1日至%d年%d月%d日，A股上市公司重要股东二级市场减持金额合计，单位亿元"
            % (d.year, d.month, d.year, d.month, d.day))
