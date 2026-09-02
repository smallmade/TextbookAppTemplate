#!/usr/bin/env python3
"""Gate 06A / M3 —— 会上屏的字面量里不许有占位符、未知符号、`nan`、开屏短横。

规范 v5.0 §6 的 M3 第一句：「零占位符 / 未知符号 / `?` / `nan` / `inf` /
开屏短横」。三款 App 的走查各抓到过这类：一条「校核」永远不会失败、涡轮
分支用错功的符号但被 guard 挡成 `--`、画面开在一列短横。

**审核员是这个 App 的第一个用户，而且只用五分钟。** 一个印着 `TODO` 或
`nan` 的画面，在审核里等同于半成品。

──────────────────────────────────────────────────────────────
判据

只看**会上屏的字面量**。这道闸门的全部难点在这里：Swift 源码里到处都是
`nan`、`?`、`TODO`——在注释里、在类型的可选标记里、在标识符里。一道对着
`Optional<Double>?` 报警的闸门，两天之内会被关掉。

所以：
  1. 先剥注释（`//` 与 `/* */`），字串字面量里的 `//` 不算注释开头；
  2. 只在剩下的**双引号字符串字面量**里找；
  3. 排除一望即知不上屏的字面量：SF Symbol 名（`Image(systemName:)`）、
     资源与文件名、`#selector` 之流、以及以 `com.` 开头的标识符；
  4. 物理里合法的 `N/A`（牛顿每安培之类的量纲写法）由上下文排除：只有当
     `N/A` 是整个字面量、或紧邻「—」「--」这类占位记号时才算命中。

「开屏一列短横」：连续两个以上 `-` 单独构成一个字面量（`"--"`、`"---"`、
`"—"`），这是本系列反复出现的「算不出来就画根横线」的痕迹。它作为**占位**
是缺陷；作为**减号或范围号**在别的字面量里出现不算。

    python tools/ci/check_ui_strings.py [--root .] [--app DIR] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 命中即未通过。(正则, 说明)。正则跑在【单个字面量的完整内容】上。
FORBIDDEN: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bTODO\b", re.I), "TODO"),
    (re.compile(r"\bFIXME\b", re.I), "FIXME"),
    (re.compile(r"\bplaceholder\b", re.I), "placeholder"),
    (re.compile(r"\blorem\b", re.I), "lorem ipsum"),
    (re.compile(r"\bTBD\b"), "TBD"),
    (re.compile(r"\bXXX\b"), "XXX"),
    (re.compile(r"\?\?\?"), "???"),
    (re.compile(r"^\s*\?\s*$"), "整个字面量就是一个问号"),
    (re.compile(r"^\s*N/A\s*$", re.I), "N/A 作为读数占位"),
    (re.compile(r"^\s*(nil|null)\s*$", re.I), "字面量 \"nil\""),
    (re.compile(r"^\s*Unknown\s*$", re.I), "Unknown"),
    (re.compile(r"^\s*[-−–—]{2,}\s*$"), "开屏一列短横（算不出来就画根横线）"),
    (re.compile(r"^\s*(nan|-?inf(inity)?)\s*$", re.I), "nan / inf 直接上屏"),
    (re.compile(r"\bnan\b", re.I), "nan 出现在会上屏的文字里"),
]

#: 这些字面量不上屏，跳过。判据是它前面那个调用/键的名字。
#
# `keyboardShortcut` is in this list because of a real false positive:
# `.keyboardShortcut("?", modifiers: .command)` is the standard binding for
# Help on macOS, and the literal is a KEY, not a label. A gate that fires on
# the platform's own Help shortcut is a gate that gets switched off.
NOT_ON_SCREEN = re.compile(
    r"(systemName|imageNamed|forResource|withExtension|named|"
    r"identifier|bundleIdentifier|keyPath|forKey|withIdentifier|"
    r"keyboardShortcut|KeyEquivalent|character|"
    r"UserDefaults|NSLocalizedString\s*\(\s*$|url|URL|scheme|host|path)"
    r"\s*:?\s*\(?\s*$")

#: 一整行都是这些的，也不上屏。
SKIP_LINE = re.compile(r"^\s*(import|@_|#if|#endif|#else|package|\.process|"
                       r"\.copy|// )")


def strip_comments(source: str) -> str:
    """去掉注释，保留字符串字面量的位置（用空格填充，行号不变）。

    手写一个小状态机而不是拿正则一把梭：`let s = "http://x"` 里的 `//`
    不是注释，而按正则去注释会把这一行的后半截连同结尾的引号一起吃掉，
    于是后面所有字面量的配对全部错位。这类「工具本身把源码看错了」的
    失败，输出看起来完全正常。
    """
    out: list[str] = []
    i, n = 0, len(source)
    in_string = False
    while i < n:
        c = source[i]
        if in_string:
            if c == "\\" and i + 1 < n:
                out.append(source[i:i + 2])
                i += 2
                continue
            out.append(c)
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and i + 1 < n and source[i + 1] == "*":
            depth = 1
            out.append("  ")
            i += 2
            while i < n and depth:
                if source.startswith("/*", i):
                    depth += 1
                    out.append("  ")
                    i += 2
                elif source.startswith("*/", i):
                    depth -= 1
                    out.append("  ")
                    i += 2
                else:
                    out.append("\n" if source[i] == "\n" else " ")
                    i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def literals(source: str) -> list[tuple[int, str, str]]:
    """会上屏的字面量：(行号, 内容, 该行原文)。"""
    text = strip_comments(source)
    found: list[tuple[int, str, str]] = []
    for match in LITERAL.finditer(text):
        line_no = text.count("\n", 0, match.start()) + 1
        line_start = text.rfind("\n", 0, match.start()) + 1
        line = text[line_start:text.find("\n", match.start())
                    if text.find("\n", match.start()) >= 0 else len(text)]
        before = text[line_start:match.start()]
        if SKIP_LINE.match(line) or NOT_ON_SCREEN.search(before):
            continue
        content = match.group(1)
        if content.startswith("com.") or content.startswith("http"):
            continue
        found.append((line_no, content, line.strip()))
    return found


def problems(source: str, where: str) -> list[str]:
    out: list[str] = []
    for line_no, content, line in literals(source):
        for pattern, why in FORBIDDEN:
            if pattern.search(content):
                out.append(f"{where}:{line_no}  {why}  → {line[:88]}")
                break
    return out


# ──────────────────────────────── 自检 ────────────────────────────────

BAD = [
    ("TODO 在会上屏的字面量里", 'Text("TODO: wire this up")'),
    ("开屏一列短横", 'Readout(value: "--")'),
    ("nan 上屏", 'Text("nan")'),
    ("整个字面量是问号", 'Label("?", systemImage: icon)'),
    ("N/A 作为读数占位", 'Text("N/A")'),
    ("Unknown", 'Text("Unknown")'),
    ("字面量 nil", 'Text("nil")'),
    ("placeholder", 'TextField("placeholder", text: $x)'),
    ("???", 'Text("value ???")'),
]
GOOD = [
    ("注释里写 TODO 不算", '// TODO: refactor later\nText("Shear stress")'),
    ("块注释里写 nan 不算", '/* returns nan when undefined */\nText("Stress")'),
    ("SF Symbol 名不上屏", 'Image(systemName: "questionmark.circle")'),
    ("Optional 的问号不是字面量", 'let x: Double? = nil'),
    ("含 // 的 URL 字面量不会把后半行吃掉",
     'let u = "http://x//y"\nText("Bending moment")'),
    ("单个减号是减号，不是占位", 'Text("a - b")'),
    ("量纲写法里的斜杠", 'Text("kN/m")'),
    ("标识符里的 nan 不算（不是字面量）", 'let nanCount = 0'),
    ("bundle id 不上屏", 'let id = "com.yudehai.app"'),
    # 实测误报，来自 MechanicsOne 的 Commands.swift：⌘? 是 macOS 的
    # Help 标准快捷键，那个字面量是一个【键】，不是标签。
    ("⌘? 是 Help 的标准快捷键，不是标签",
     '.keyboardShortcut("?", modifiers: .command)'),
]


def self_test() -> int:
    ok = True
    for label, source in BAD:
        caught = bool(problems(source, "s.swift"))
        ok &= caught
        print(f"  {'PASS' if caught else 'FAIL'}  拒绝  {label}")
    for label, source in GOOD:
        found = problems(source, "s.swift")
        quiet = not found
        ok &= quiet
        print(f"  {'PASS' if quiet else 'FAIL'}  放行  {label}"
              + ("" if quiet else f"   ← 误报：{found}"))
    print("\n自检通过——闸门既不漏报也不乱叫" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--app", type=Path, default=None,
                    help="界面层目录；不给就读 ci.toml 的 swift_app_dir")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_ui_strings.py 自检")
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
    hits: list[str] = []
    seen = 0
    for path in files:
        source = path.read_text(encoding="utf-8", errors="ignore")
        seen += len(literals(source))
        hits += problems(source, str(path.relative_to(root)))

    print(checked(seen, "个会上屏的字面量", f"{len(files)} 个 .swift"))
    if seen == 0:
        print("✗ 一个上屏字面量都没扫到——这不是「界面干净」，这是没检查。")
        return 1
    if hits:
        print(f"✗ {len(hits)} 处占位符 / 未知符号 / 短横：")
        for line in hits:
            print(f"    {line}")
        print("  审核员是这个 App 的第一个用户，而且只用五分钟。")
        return 1
    print(f"✓ {seen} 个上屏字面量里没有占位符、未知符号、nan/inf 或开屏短横")
    return 0


if __name__ == "__main__":
    sys.exit(main())
