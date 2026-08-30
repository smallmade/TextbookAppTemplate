#!/usr/bin/env python3
"""Gate 09 —— 打包脚本之间必须互相对得上。

    python tools/ci/check_packaging.py

规范的 Gate 09 有一条：**「安装器脚本里的路径与构建脚本实际产出一致
（有自动测试守着）」**。这就是那个自动测试。

它守四件事，每一件坏掉的方式都不一样：

1. **名字对不上。** PyInstaller 的 `COLLECT(name=...)` 决定 `dist/` 下的目录
   名，Inno Setup 的 `[Files] Source:` 从那个目录取。改一个忘了改另一个，
   编译安装器时报「找不到文件」——如果那时 `dist/` 恰好还留着上一次的目录，
   它会**安静地打包上一次的构建**。

2. **GPL-only 的排除项被删掉。** 那三行是 Qt 版 spec 存在的理由；删掉不会
   报错，只会让下一次打包把 GPL 组件收进去。

3. **Windows 安装器不再是 per-user。** `PrivilegesRequired=lowest` 与
   `DefaultDirName` 必须同时对。只改一个，安装器会在写入时失败，而失败发生
   在进度条走到一半的时候。

4. **两个 macOS 版共用一个 Bundle ID**，或者和 App Store 版撞上。撞了会互相
   覆盖：装了桌面版，App Store 版的更新就装不上。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 路径从命令行来，不从脚本自己的位置推。
#
# `tools/ci` 在每个项目里是**指向共享模板的符号链接**，所以
# `Path(__file__).resolve()` 会落在模板目录里，而不是调用它的那个项目里。
# 第一版就是这么写的，于是它在模板目录下找 `packaging/`，报「文件不存在」
# ——而 `packaging/` 明明就在项目里躺着。
#
# 顺带把这道闸门变成真正可复用的：七款 App 的 spec 文件名各不相同，
# 一个把名字写死的闸门只服务第一款。
GPL_ONLY = ("QtCharts", "QtDataVisualization", "QtNetworkAuth",
            "QtVirtualKeyboard")


def collect_name(spec: Path) -> str | None:
    match = re.search(r"COLLECT\([^)]*name=\"([^\"]+)\"", spec.read_text(
        encoding="utf-8"), re.S)
    return match.group(1) if match else None


def bundle_id(spec: Path) -> str | None:
    match = re.search(r'bundle_identifier="([^"]+)"',
                      spec.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plain-spec", type=Path, required=True,
                    help="不带 Qt 的那一版 PyInstaller spec")
    ap.add_argument("--qt-spec", type=Path, required=True)
    ap.add_argument("--inno", type=Path, required=True)
    ap.add_argument("--store-bundle-id", required=True,
                    help="App Store 版的 bundle id，用来查撞号")
    args = ap.parse_args()
    TK_SPEC, QT_SPEC, INNO = args.plain_spec, args.qt_spec, args.inno
    failed = False

    for path in (TK_SPEC, QT_SPEC, INNO):
        if not path.exists():
            print(f"✗ 缺 {path}")
            return 1

    # 1 —— 安装器取的目录名，就是 PyInstaller 产出的目录名。
    produced = collect_name(TK_SPEC)
    inno = INNO.read_text(encoding="utf-8")
    sources = re.findall(r'Source:\s*"\.\.\\dist\\([^\\"]+)', inno)
    if not produced:
        print("✗ tk spec 里读不到 COLLECT 的 name")
        failed = True
    elif produced not in sources:
        print(f"✗ 安装器从 dist\\{sources} 取文件，而构建产出的是 "
              f"dist/{produced}")
        print("  编译时会报「找不到文件」——除非 dist/ 里恰好留着上一次的"
              "目录，那样它会安静地打包上一次的构建。")
        failed = True
    else:
        print(f"✓ 安装器路径与构建产物一致（dist/{produced}）")

    # 2 —— GPL-only 的排除项还在。
    qt = QT_SPEC.read_text(encoding="utf-8")
    missing = [name for name in GPL_ONLY if name not in qt]
    if missing:
        print(f"✗ Qt spec 的 excludes 里缺了 GPL-only 模块：{missing}")
        print("  删掉它们不会报错，只会让下一次打包把 GPL 组件收进去。")
        failed = True
    else:
        print(f"✓ Qt spec 排除了全部 {len(GPL_ONLY)} 个 GPL-only 模块")

    tk = TK_SPEC.read_text(encoding="utf-8")
    if "PySide6" not in tk or '"PySide6"' not in tk:
        print("✗ tk spec 没有排除 PySide6 —— 这一版的卖点就是不带 Qt")
        failed = True
    else:
        print("✓ tk spec 排除了 Qt（这一版没有许可问题）")

    # 3 —— Windows 安装器是 per-user。
    if "PrivilegesRequired=lowest" not in inno:
        print("✗ 安装器要求管理员权限。目标用户多半不是管理员——"
              "一个要求提权的安装器是他们根本跑不起来的。")
        failed = True
    elif "{localappdata}" not in inno and "{userappdata}" not in inno:
        print("✗ PrivilegesRequired=lowest 但装到了需要提权的位置。"
              "两者必须同时对，否则会在写入时失败——而那发生在进度条走到"
              "一半的时候。")
        failed = True
    else:
        print("✓ Windows 安装器是 per-user，无需管理员权限")

    # 4 —— Bundle ID 三方互不相同。
    ids = {"tk 桌面版": bundle_id(TK_SPEC), "qt 桌面版": bundle_id(QT_SPEC)}
    # App Store 版的 plist 里放的是 Xcode 构建变量，真值在工程设置里，
    # 所以由调用方传进来。
    ids["App Store 版"] = args.store_bundle_id
    seen: dict[str, str] = {}
    clash = False
    for who, value in ids.items():
        if value is None:
            print(f"✗ {who} 读不到 bundle identifier")
            failed = True
            continue
        if value in seen:
            print(f"✗ {who} 与 {seen[value]} 共用 bundle id「{value}」")
            print("  相同的话两个版本会互相覆盖：装了一个，另一个的更新就"
                  "装不上。")
            clash = True
        seen[value] = who
    if clash:
        failed = True
    elif not failed:
        print("✓ 三个 bundle id 互不相同：")
        for who, value in ids.items():
            print(f"      {who:12s} {value}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
