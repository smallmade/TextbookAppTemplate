#!/usr/bin/env python3
"""闸门 —— 正典声明的每一个 v1.0 输出，用户是不是真的到得了。

阶段 04 的 App 那一侧。它问的不是「算得对吗」，也不是「有没有实现」，
而是：**打开这个 App 的人，能不能走到这个量前面。**

写它的理由是一张手写的表。`docs/coverage-audit-posable.csv` 曾经断言
「35 个 v1.0 模块，35 个都有画面收留，一个孤儿也没有」。那张表是照着
**正典的声明**列的，不是照着**画面的实现**——它把 M01 的输入写成
`P, A, V, A_b, L, delta, sigma_fail, sigma_allow`，而 Axial 画面上
`V` 与 `A_b` 两个输入框根本不存在。

于是有两个 v1.0 模块——超静定轴向构件、非均匀与超静定扭转——内核实现了、
conformance 比对过、对等测试点过名、法律隔离扫过，**而界面上没有任何一个
控件能把那种题录进去**。前面每一道闸门都是绿的。

判据是**可达性**，不是名字：从 `MechanicsOneApp` 的全部源码出发，沿
`MechanicsKit` 里函数体的调用关系求闭包；正典每个输出的 `function` 指针
落在闭包里，才算到得了。注释先剥掉——一个只出现在注释里的名字不是调用。

这个判据会漏报（保守），不会误报：
  * 界面自己内联算了同一个量（不调那个 kernel 函数），会被记成「到不了」，
    而其实屏幕上有。所以 `partial` 只报告、不失败。
  * 一个模块的输出**一个都到不了**，则无论怎么内联都说明没有入口——
    这一档才失败。

    python tools/ci/check_screen_reachability.py [--root .] [--write] [--self-test]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
COMMENT_LINE = re.compile(r"//[^\n]*")
DECLARATION = re.compile(r"\b(?:func|var|let)\s+([A-Za-z_][A-Za-z0-9_]*)")
#: Anything that can own a brace. Used only to bound the search for a body --
#: a stored property must not be allowed to adopt the brace of the type that
#: follows it.
BOUNDARY = re.compile(r"\b(?:func|var|let|init|subscript|enum|struct|class"
                      r"|extension|protocol|actor)\b")
IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def swiftify(snake: str) -> str:
    """``bearing_stress`` -> ``bearingStress``, the transliteration rule."""
    head, *rest = snake.split("_")
    return head + "".join(word.capitalize() for word in rest)


def without_comments(text: str) -> str:
    return COMMENT_LINE.sub(" ", COMMENT_BLOCK.sub(" ", text))


def bodies(text: str) -> dict[str, str]:
    """``{declared name: its brace-matched body}``.

    Brace matching rather than a fixed window: a window spills into the next
    declaration, and then every name reaches every other name and the whole
    check reports zero problems. The first version did exactly that.

    The opening brace is searched for only up to the next thing that could own
    one -- another declaration, or a type. Two versions were wrong here before
    this bound existed:

    * unbounded, ``let standardCases: [String] = [...]`` (a bracket body, not a
      brace one) adopted the brace of some later function;
    * bounded only by the next ``func``/``var``/``let``, the stored property
      ``public let right: Double`` reached past the closing of its own struct
      and adopted the brace of ``enum TorsionSolve``, making every solver in
      that enum look reachable from any screen that mentions ``right``.

    A ``}`` appearing before the candidate brace means the declaration has
    already ended, so that is rejected too.
    """
    found: dict[str, str] = {}
    for match in DECLARATION.finditer(text):
        following = BOUNDARY.search(text, match.end())
        limit = following.start() if following else len(text)
        start = text.find("{", match.end(), limit)
        if start < 0 or "}" in text[match.end():start]:
            continue
        depth, index = 0, start
        while index < len(text):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        found[match.group(1)] = found.get(match.group(1), "") + " " + text[start:index]
    return found


def reachable(app_sources: list[str], kit_sources: list[str]) -> set[str]:
    """Every identifier the application can arrive at, transitively."""
    kit = bodies(" ".join(without_comments(t) for t in kit_sources))
    seen = set(IDENTIFIER.findall(" ".join(without_comments(t) for t in app_sources)))
    frontier = set(seen)
    while frontier:
        following: set[str] = set()
        for name in frontier:
            if name in kit:
                following |= set(IDENTIFIER.findall(kit[name])) - seen
        seen |= following
        frontier = following
    return seen


def classify(spec: dict, seen: set[str]) -> list[tuple[str, str, list[str], list[str]]]:
    rows = []
    for module in spec["modules"]:
        if module.get("tier") != "core" and module.get("release") != "v1.0":
            continue
        outputs = [(o["symbol"], o["function"])
                   for o in module.get("outputs", []) if o.get("function")]
        if not outputs:
            continue
        arrived = [s for s, f in outputs
                   if swiftify(f.rsplit(".", 1)[-1]) in seen]
        missing = [s for s, f in outputs
                   if swiftify(f.rsplit(".", 1)[-1]) not in seen]
        rows.append((module["id"], module["title"], arrived, missing))
    return rows


HEADER = """\
# 每个 v1.0 模块的输出，界面上到不到得了 —— 【实测】，不是照正典抄的
#
# 由 tools/ci/check_screen_reachability.py --write 生成。上一版是手写的，
# 它照正典的声明列输入，于是把两个界面上根本没有入口的模块记成「有画面收留」。
#
# reach 列：full 全部输出可达 · partial 部分可达 · none 一个也到不了
# unreachable 列：正典声明了、而从 App 走不到的输出符号
"""


def write_table(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(HEADER)
        writer = csv.writer(handle)
        writer.writerow(["module", "title", "reach", "reached", "unreachable"])
        for mid, title, arrived, missing in rows:
            reach = "full" if not missing else ("none" if not arrived else "partial")
            writer.writerow([mid, title, reach, " ".join(arrived), " ".join(missing)])


def self_test() -> int:
    """已知样本：一个可达、一个经由中间函数可达、一个到不了。"""
    app = ["struct S { var body: some View { Kit.shown() } }"]
    kit = ["enum Kit { static func shown() -> Double { helper() }\n"
           "  static func helper() -> Double { deep() }\n"
           "  static func deep() -> Double { 1 }\n"
           "  static func orphan() -> Double { 2 } }"]
    seen = reachable(app, kit)
    checks = [("直接调用", "shown", True), ("经由一层", "helper", True),
              ("经由两层", "deep", True), ("没人调用", "orphan", False)]
    ok = True
    for label, name, want in checks:
        good = (name in seen) == want
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {'可达' if want else '不可达'}  {label}")

    # 注释里的名字不算调用——否则一句「// orphan is unused」就能让它变可达
    commented = reachable(["// orphan\n/* orphan */"], kit)
    good = "orphan" not in commented
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  不可达  只出现在注释里的名字")

    # 花括号配对：窗口式扫描会让 orphan 因为紧挨着 deep 而被算成可达
    good = "orphan" not in reachable(["Kit.deep()"], kit)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  不可达  相邻声明不因窗口溢出而可达")

    # 无花括号体的声明（方括号字面量）不得认领后面那个函数的花括号
    bracketed = ["Kit.names"]
    kit2 = ["enum Kit { static let names: [String] = [\"a\", \"b\"]\n"
            "  static func faraway() -> Double { hidden() }\n"
            "  static func hidden() -> Double { 3 } }"]
    good = "hidden" not in reachable(bracketed, kit2)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  不可达  方括号字面量不认领后面的函数体")

    # 存储属性不得越过自己所在类型的右花括号，去认领下一个 enum 的体
    kit3 = ["struct Pair { public let right: Double }\n"
            "enum Solver { static func buried() -> Double { 4 } }"]
    good = "buried" not in reachable(["Pair(right: 1)"], kit3)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  不可达  存储属性不认领下一个类型的体")
    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--write", action="store_true", help="刷新 posable 表")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_screen_reachability.py 自检")
        return self_test()

    root = args.root.resolve()
    app_dir = root / "swift" / "Sources" / "MechanicsOneApp"
    kit_dir = root / "swift" / "Sources" / "MechanicsKit"
    spec_path = root / "spec" / "specification.json"
    if not (app_dir.is_dir() and kit_dir.is_dir() and spec_path.is_file()):
        print("尚不适用：Swift 侧或正典还不在 —— 阶段 05 之前正常", file=sys.stderr)
        return 2

    rows = classify(
        json.loads(spec_path.read_text(encoding="utf-8")),
        reachable([p.read_text("utf-8") for p in app_dir.rglob("*.swift")],
                  [p.read_text("utf-8") for p in kit_dir.rglob("*.swift")]))

    if args.write:
        target = root / "docs" / "coverage-audit-posable.csv"
        write_table(target, rows)
        print(f"已写出 {target.relative_to(root)}（{len(rows)} 个模块）")

    none = [(i, t) for i, t, a, m in rows if not a]
    partial = [(i, t, m) for i, t, a, m in rows if a and m]
    print(f"v1.0 模块 {len(rows)} 个 · 全部输出可达 "
          f"{len(rows) - len(none) - len(partial)} · 部分 {len(partial)} · "
          f"一个也到不了 {len(none)}")
    for mid, title, missing in partial:
        print(f"  − {mid} {title[:40]:<40} 声明了但走不到：{', '.join(missing)}")
    if none:
        print(f"\n✗ {len(none)} 个 v1.0 模块，界面上没有任何入口：")
        for mid, title in none:
            print(f"    {mid}  {title}")
        print("  内核实现了、conformance 比对过、对等测试点过名——"
              "而用户走不到。前面每一道闸门都会是绿的。")
        return 1
    print("✓ 每个 v1.0 模块都至少有一个输出到得了界面")
    return 0


if __name__ == "__main__":
    sys.exit(main())
