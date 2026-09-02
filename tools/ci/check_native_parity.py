#!/usr/bin/env python3
"""Gate 06A / M5 —— 原生对标：菜单、帮助、关于、设置、导出，每一项都要有落点。

规范 v5.0 §7.2「原生对标清单」逐项化。这道闸门只查**最低限度的五项存在性**，
每一项报出它找到的落点（文件:行）：

    .commands{}   —— Mac 菜单栏；没有它，File/Edit/View/Help 全是系统默认，
                     而 PlotOne 正是因为「打开就是一个 File 菜单全灰」被
                     GL 2.1(a) 拒过
    Help 菜单项   —— 使用手册 / 理论手册的入口。规范：两册进 App 内 Help
    About         —— 版本、公有领域来源致谢、支持链接
    Settings 场景 —— 单位制、位数、默认材料
    导出入口      —— 图 → PNG/PDF/SVG，表 → CSV。**从 v5.0 起是必做项**
                     （负责人 2026-09-02：「用最完整的方式实现」）

**存在性不等于好用。** 这道闸门抓的是「整项缺失」，不是质量——质量由 06C
的评测和设备矩阵评分表管。但整项缺失是本系列反复发生的事，而且它在
「编译通过、测试全绿」的日志里完全看不见。

    python tools/ci/check_native_parity.py [--root .] [--app DIR] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 项名 → (正则, 缺失时印的一句话)
#:
#: 每条都是**多种合法写法的并集**，因为 SwiftUI 里同一件事有好几种写法，
#: 而一道只认一种写法的闸门会对着正确的代码报红。
REQUIRED: dict[str, tuple[re.Pattern, str]] = {
    # 只认 `.commands {` 与 `CommandMenu(`。
    #
    # 第一版还认 `CommandGroup(` 和 `: Commands`，于是把 `.commands {` 整段
    # 删掉之后闸门仍然放行——因为定义 Commands 的那个 struct 还在。**定义了
    # 一组菜单命令、却没有把它挂进 Scene**，正是这一项要抓的形状：编译通过，
    # 测试全绿，菜单栏是系统默认的。自检里那条「只抽掉 .commands{}」的样本
    # 就是被它漏掉的。
    ".commands{}": (
        re.compile(r"\.commands\s*\{|CommandMenu\s*\("),
        "Mac 菜单栏。没有它，菜单全是系统默认——PlotOne 因「打开就是一个"
        "全灰的 File 菜单」被 GL 2.1(a) 拒过"),
    "Help 菜单项": (
        re.compile(r"CommandGroup\s*\(\s*replacing:\s*\.help|"
                   r"CommandGroup\s*\(\s*after:\s*\.help|"
                   r"\.help\s*\)|helpMenu|HelpViewer|"
                   r'CommandMenu\s*\(\s*"Help"'),
        "使用手册与理论手册的 App 内入口（规范 v5.0 §5.10：两册进 Help）"),
    "About": (
        re.compile(r"replacing:\s*\.appInfo|AboutView|showAbout|"
                   r'"About '),
        "关于面板：版本、公有领域来源致谢、支持链接"),
    "Settings 场景": (
        re.compile(r"\bSettings\s*\{|SettingsView|SettingsLink|"
                   r"replacing:\s*\.appSettings|"
                   r'CommandGroup\s*\(\s*replacing:\s*\.appSettings'),
        "设置：单位制、位数、默认工质/材料"),
    "导出入口": (
        re.compile(r"ShareLink\s*\(|\.fileExporter\s*\(|NSSavePanel|"
                   r"UTType\.|\bexportPNG\b|\bexportPDF\b|\bexportCSV\b|"
                   r"NSPasteboard|UIPasteboard"),
        "导出：图 → PNG/PDF/SVG，表 → CSV，复制到剪贴板。"
        "v5.0 起是必做项（可交付输出是五条护城河之一）"),
}


def find(sources: dict[str, str], pattern: re.Pattern) -> list[str]:
    """每一处落点，写成 `文件:行`。"""
    out: list[str] = []
    for name, text in sources.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            out.append(f"{name}:{line}")
    return out


def audit(sources: dict[str, str]) -> dict[str, list[str]]:
    return {item: find(sources, pattern)
            for item, (pattern, _) in REQUIRED.items()}


# ──────────────────────────────── 自检 ────────────────────────────────

COMPLETE = {"App.swift": """
struct A: App {
  var body: some Scene {
    WindowGroup { RootView() }.commands { MechanicsCommands() }
    Settings { SettingsView() }
  }
}
struct MechanicsCommands: Commands {
  var body: some Commands {
    CommandGroup(replacing: .appInfo) { Button("About X") { } }
    CommandGroup(replacing: .help) { Button("User Manual") { } }
  }
}
ShareLink(item: png)
"""}


def self_test() -> int:
    ok = True
    result = audit(COMPLETE)
    good = all(result.values())
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  五项俱全的 App"
          + ("" if good else f"   ← 漏判：{[k for k, v in result.items() if not v]}"))

    # 已知会失败的样本：每次抽掉一项，闸门必须只报那一项。
    for missing in REQUIRED:
        source = COMPLETE["App.swift"]
        cut = {
            ".commands{}": (".commands { MechanicsCommands() }", ""),
            "Help 菜单项": ('CommandGroup(replacing: .help) '
                             '{ Button("User Manual") { } }', ""),
            "About": ('CommandGroup(replacing: .appInfo) '
                      '{ Button("About X") { } }', ""),
            "Settings 场景": ("Settings { SettingsView() }", ""),
            "导出入口": ("ShareLink(item: png)", ""),
        }[missing]
        stripped = source.replace(*cut)
        result = audit({"App.swift": stripped})
        absent = [k for k, v in result.items() if not v]
        good = absent == [missing]
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  抓到  只抽掉「{missing}」"
              + ("" if good else f"   ← 实际报缺：{absent}"))

    empty = audit({"Empty.swift": "struct V: View { }"})
    good = not any(empty.values())
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  一个都没有的空壳")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--app", type=Path, default=None,
                    help="界面层目录；不给就读 ci.toml 的 swift_app_dir")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_native_parity.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    app_dir = args.app or cfg.path("swift_app_dir")
    if app_dir is None or not app_dir.is_dir():
        if not (root / "swift" / "Sources").is_dir():
            print("尚不适用：界面层还没建（阶段 06 之前正常）", file=sys.stderr)
            return 2
        print(f"✗ 摸不到界面层目录 {app_dir} —— 在 ci.toml 里写 swift_app_dir")
        return 1

    files = sorted(app_dir.rglob("*.swift"))
    sources = {str(p.relative_to(root)): p.read_text(encoding="utf-8",
                                                     errors="ignore")
               for p in files}
    result = audit(sources)

    print(checked(len(REQUIRED), "项原生对标", f"{len(files)} 个 .swift"))
    if not files:
        print("✗ 界面层里一个 .swift 都没有——这不是通过，这是没检查。")
        return 1

    missing = []
    for item, (_, why) in REQUIRED.items():
        where = result[item]
        if where:
            shown = ", ".join(where[:3]) + (" …" if len(where) > 3 else "")
            print(f"  ✓ {item:<14} {shown}")
        else:
            missing.append((item, why))
            print(f"  ✗ {item:<14} 一处落点都没有")
    if missing:
        print(f"\n✗ {len(missing)} / {len(REQUIRED)} 项原生对标缺失：")
        for item, why in missing:
            print(f"    {item}")
            print(f"        {why}")
        return 1
    print(f"\n✓ {len(REQUIRED)} 项原生对标都找得到落点")
    return 0


if __name__ == "__main__":
    sys.exit(main())
