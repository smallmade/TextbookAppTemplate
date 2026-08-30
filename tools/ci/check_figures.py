#!/usr/bin/env python3
"""闸门 —— 每一个出货画面都必须有属于它自己的图。

**这一条是被同一个缺陷咬第二次才写的。**

第一次：图形按正典的「族」分派，于是每个应力画面都摆一个莫尔圆、每个梁画面
都摆一条弯矩图——26 个画面里 10 个的图形栏是空的或没有意义。逐屏走查抓到它，
**当时是手工清干净的，没有变成闸门。**

第二次：清干净之后又出货了 19 个画面。`switch module.id` 的 `default` 分支
一律画应力状态圆，于是挡土墙、弯扭屈曲、近似屈曲三个画面各自摆着一个与内容
毫无关系的莫尔圆。图**不是空的**，所以看起来没坏；而没有任何一道闸门在看图。

> 一次手工清理修的是那 10 个画面；一道闸门修的是**这一类**。
> 两者的差别就是这 19 个画面。

判据：正典里每一个 v1.0 module，要么在 `FigureColumn.swift` 的 `switch` 里
有具名 `case`，要么在 `Evaluate.openingFamily` 里有条目（那类画面的输入是一个
结构，图按形状画）。落进 `default` 的一律未通过。

`--self-test` 拿三份已知会失败的输入喂自己，证明它真的会叫。

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GREEN, RED, BOLD, OFF = "\033[32m", "\033[31m", "\033[1m", "\033[0m"

FIGURE = Path("swift/Sources/StructureMechOneApp/FigureColumn.swift")
EVALUATE = Path("swift/Sources/StructureKit/Presentation/Evaluate.swift")


def named_cases(source: str) -> set[str]:
    """Module ids with a `case` of their own, before the `default`.

    Sliced at `default:` on purpose: a `case` written *after* it is unreachable,
    and counting it would be the gate agreeing with a bug.
    """
    if "switch module.id {" not in source:
        return set()
        # A rewritten dispatch is not a silent pass; `main` treats an empty set
        # as "nothing is named", which fails loudly against a non-empty canon.
    body = source.split("switch module.id {", 1)[1].split("default:", 1)[0]
    return set(re.findall(r'"([a-z_0-9]+)"', body))


def structural(source: str) -> set[str]:
    """Module ids whose figure is the structure the reader built."""
    # Anchored on the `= [` of the assignment, not on the first `[` after the
    # name -- that one belongs to the type annotation `[String: String]`, and
    # splitting there quietly returned an empty table for every real file while
    # still reporting success. The self-test's "accepts a well-formed input"
    # case is what caught it.
    match = re.search(r"openingFamily[^=\[]*(?:\[[^\]]*\])?[^=]*=\s*\[(.*)",
                      source, re.DOTALL)
    if match is None:
        return set()
    table = match.group(1).split("\n    ]", 1)[0]
    return set(re.findall(r'"([a-z_0-9]+)"\s*:', table))


def check(shipping: list[str], figure: str, evaluate: str) -> list[str]:
    """Every complaint, as human-readable lines."""
    drawn = named_cases(figure) | structural(evaluate)
    return [module for module in shipping if module not in drawn]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = args.root.resolve()
    spec_path = root / "spec" / "specification.json"
    if not spec_path.is_file():
        print(f"尚不适用：还没有 {spec_path.name}", file=sys.stderr)
        return 2
    figure_path, evaluate_path = root / FIGURE, root / EVALUATE
    if not figure_path.is_file() or not evaluate_path.is_file():
        print("尚不适用：Swift 界面还没建（找不到 FigureColumn.swift）",
              file=sys.stderr)
        return 2

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    shipping = [m["id"] for m in spec["modules"]
                if str(m.get("release", "")).startswith("v1")]
    figure = figure_path.read_text(encoding="utf-8")
    evaluate = evaluate_path.read_text(encoding="utf-8")

    # 兜底分支本身也不许再画一个「看起来合理」的东西——那正是它藏住三个画面
    # 的方式。它必须画一句「这个画面没有声明图」，让走查一眼看见。
    print()
    print(f"{BOLD}闸门 · 每个画面都有自己的图{OFF}")
    fail = 0
    if "drawNoFigureDeclared" not in figure:
        print(f"  {RED}✗{OFF} 兜底分支画了一个看起来合理的图，"
              f"而不是说出「没有声明」——那正是上次没被发现的原因")
        fail += 1
    else:
        print(f"  {GREEN}✓{OFF} 兜底分支自曝其短，不再假装有图")

    missing = check(shipping, figure, evaluate)
    if missing:
        print(f"  {RED}✗{OFF} {len(missing)} / {len(shipping)} 个出货画面没有自己的图：")
        for module in missing:
            print(f"      {module}")
        fail += 1
    else:
        drawn = len(named_cases(figure) & set(shipping))
        shaped = len(structural(evaluate) & set(shipping))
        print(f"  {GREEN}✓{OFF} {len(shipping)} 个出货画面各有其图"
              f"（具名 {drawn} · 按结构画 {shaped}）")

    print()
    if fail:
        print(f"{RED}{BOLD}未通过：{fail} 项。{OFF}\n")
        return 1
    print(f"{GREEN}{BOLD}图形覆盖通过。{OFF}\n")
    return 0


#: 三份已知会失败的输入，各自对应一种真实发生过的漏法。
BAD = [
    ("落进 default", ["a", "b"],
     'switch module.id {\ncase "a": drawA()\ndefault: drawStateOfStress()\n}',
     'openingFamily: [String: String] = [ ]'),
    ("case 写在 default 之后（不可达）", ["a"],
     'switch module.id {\ndefault: drawX()\ncase "a": drawA()\n}',
     'openingFamily: [String: String] = [ ]'),
    ("dispatch 被改写，一个都没匹配到", ["a"],
     'if module.id == "a" { drawA() }',
     'openingFamily: [String: String] = [ ]'),
]


def self_test() -> int:
    ok = True
    for why, shipping, figure, evaluate in BAD:
        caught = bool(check(shipping, figure, evaluate))
        print(f"  {'PASS' if caught else 'FAIL'}  拒绝：{why}")
        ok &= caught

    good = check(["a", "b"],
                 'switch module.id {\ncase "a": drawA()\ndefault: x()\n}',
                 'openingFamily: [String: String] = [ "b": "truss" ]')
    print(f"  {'PASS' if not good else 'FAIL'}  ----  接受两种都算数的写法")
    ok &= not good

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败——闸门不会报警")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
