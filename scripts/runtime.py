# -*- coding: utf-8 -*-
"""运行时探测：在任意机器上找到 node / node_modules / Chrome。

写死某台机器的绝对路径是这类脚本最常见的翻车原因——换台电脑就跑不动。
这里统一按「环境变量 → PATH → 常见安装位置 → 工具自带运行时」的顺序找，
找不到返回 None，由调用方给出能照着做的报错。

单独运行可直接查看本机探测结果：
    python scripts/runtime.py
"""
import glob
import os
import shutil
import sys

# 环境变量优先级：排在前面的先认
NODE_ENV_KEYS = ("THERMO_NODE", "NODE_EXE", "NODE")
NODE_MODULES_ENV_KEYS = ("THERMO_NODE_MODULES", "NODE_PATH")
CHROME_ENV_KEYS = ("THERMO_CHROME", "WB_CHROME", "CHROME_PATH", "CHROME_EXE")

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def _home(*parts):
    return os.path.join(os.path.expanduser("~"), *parts)


def _env_path(keys, want_dir=False):
    for k in keys:
        v = os.environ.get(k)
        if not v:
            continue
        # NODE_PATH 允许用 ; 或 : 分隔多个目录，逐个试
        for piece in str(v).replace(";", os.pathsep).split(os.pathsep):
            piece = piece.strip()
            if not piece:
                continue
            if want_dir and os.path.isdir(piece):
                return piece
            if not want_dir and os.path.isfile(piece):
                return piece
    return None


def _first(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def _glob_first(patterns):
    for pat in patterns:
        for p in sorted(glob.glob(pat), reverse=True):  # 版本号大的排前面
            if os.path.exists(p):
                return p
    return None


def find_node():
    """返回 node 可执行文件路径，找不到返回 None。"""
    hit = _env_path(NODE_ENV_KEYS)
    if hit:
        return hit

    hit = shutil.which("node")
    if hit:
        return hit

    exe = "node.exe" if IS_WIN else "node"
    cands = []

    # 各家工具自带的 node（WorkBuddy / nvm / volta / fnm / asdf）
    cands += sorted(glob.glob(_home(".workbuddy", "binaries", "node", "versions", "*", exe)),
                    reverse=True)
    cands += sorted(glob.glob(_home(".nvm", "versions", "node", "*", "bin", exe)), reverse=True)
    cands += sorted(glob.glob(_home(".volta", "bin", exe)))
    cands += sorted(glob.glob(_home(".asdf", "installs", "nodejs", "*", "bin", exe)), reverse=True)
    cands += sorted(glob.glob(_home("AppData", "Roaming", "fnm", "node-versions", "*", "installation", exe)),
                    reverse=True)
    cands += sorted(glob.glob(_home("AppData", "Roaming", "nvm", "v*", exe)), reverse=True)

    if IS_WIN:
        cands += [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "nodejs", exe),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "nodejs", exe),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "nodejs", exe),
            os.path.join(os.environ.get("APPDATA", ""), "npm", exe),
            _home("scoop", "apps", "nodejs", "current", exe),
            r"C:\ProgramData\chocolatey\bin\node.exe",
        ]
    elif IS_MAC:
        cands += ["/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node"]
    else:
        cands += ["/usr/local/bin/node", "/usr/bin/node", "/snap/bin/node"]

    return _first(cands)


def find_node_modules():
    """返回能找到 playwright-core 的 node_modules 目录，找不到返回 None。"""
    hit = _env_path(NODE_MODULES_ENV_KEYS, want_dir=True)
    if hit and os.path.isdir(os.path.join(hit, "playwright-core")):
        return hit

    node = find_node()
    cands = [
        os.path.join(os.getcwd(), "node_modules"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "node_modules"),
        _home(".workbuddy", "binaries", "node", "workspace", "node_modules"),
        # 全局安装：<node 前缀>/node_modules
        os.path.join(os.path.dirname(os.path.dirname(node)), "node_modules") if node else None,
        os.path.join(os.path.dirname(os.path.dirname(node)), "lib", "node_modules") if node else None,
    ]
    if IS_WIN and node:
        cands.append(os.path.join(os.path.dirname(node), "node_modules"))

    hit = _first(cands)
    if hit and os.path.isdir(os.path.join(hit, "playwright-core")):
        return hit
    return None


def find_chrome():
    """返回可用的 Chrome / Chromium / Edge 可执行文件路径，找不到返回 None。"""
    hit = _env_path(CHROME_ENV_KEYS)
    if hit:
        return hit

    exe = "chrome.exe" if IS_WIN else "chrome"
    cands = []

    # 1) 浏览器自动化工具自带的 Chromium
    cands += sorted(glob.glob(_home(".agent-browser", "browsers", "chrome-*", exe)), reverse=True)
    if IS_WIN:
        cands += sorted(glob.glob(_home("AppData", "Local", "ms-playwright", "chromium-*", "chrome-win", "chrome.exe")),
                        reverse=True)
    elif IS_MAC:
        cands += sorted(glob.glob(_home("Library", "Caches", "ms-playwright", "chromium-*", "chrome-mac*", "*.app",
                                       "Contents", "MacOS", "Chromium")), reverse=True)
    else:
        cands += sorted(glob.glob(_home(".cache", "ms-playwright", "chromium-*", "chrome-linux", "chrome")),
                        reverse=True)

    # 2) 系统安装的 Chrome
    if IS_WIN:
        cands += [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Google", "Chrome", "Application", exe),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Google", "Chrome",
                         "Application", exe),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", exe),
        ]
    elif IS_MAC:
        cands += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        cands += ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]

    hit = _first(cands)
    if hit:
        return hit

    # 3) 兜底：Windows 上 Edge 也是 Chromium 内核，能出图
    if IS_WIN:
        return _first([
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                         "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                         "Microsoft", "Edge", "Application", "msedge.exe"),
        ])
    return None


NODE_HINT = (
    "没找到 node。三种解法任选：\n"
    "  1) 装 Node.js（https://nodejs.org，装完重开终端让 PATH 生效）\n"
    "  2) 已有 node 但不在 PATH：设环境变量 THERMO_NODE=<node 可执行文件绝对路径>\n"
    "  3) 用绝对路径调用：<node> scripts/build.py ..."
)
CHROME_HINT = (
    "没找到 Chrome / Chromium。三种解法任选：\n"
    "  1) 装 Google Chrome\n"
    "  2) 已有但不在默认位置：设环境变量 THERMO_CHROME=<浏览器可执行文件绝对路径>\n"
    "  3) npx playwright install chromium 装一份 Playwright 自带的"
)
NODE_MODULES_HINT = (
    "没找到 playwright-core。任选：\n"
    "  1) 在本 skill 目录执行 npm i playwright-core\n"
    "  2) 全局装：npm i -g playwright-core，再把 THERMO_NODE_MODULES 指向全局 node_modules\n"
    "  3) 已装在别处：设环境变量 THERMO_NODE_MODULES=<含 playwright-core 的 node_modules 目录>"
)


def _main():
    node = find_node()
    mods = find_node_modules()
    chrome = find_chrome()
    print("平台       %s" % sys.platform)
    print("Python     %s" % sys.version.split()[0])
    print("node       %s" % (node or "未找到"))
    print("py 版本    %s" % (os.popen('"%s" -v' % node).read().strip() if node else "—"))
    print("node_mods  %s" % (mods or "未找到（playwright-core）"))
    print("Chrome     %s" % (chrome or "未找到"))
    bad = False
    for value, hint in ((node, NODE_HINT), (mods, NODE_MODULES_HINT), (chrome, CHROME_HINT)):
        if not value:
            bad = True
            print("\n" + hint)
    if not bad:
        print("\n运行时齐了，可以取数出图。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_main())
