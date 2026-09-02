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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

GREEN, RED, BOLD, OFF = "\033[32m", "\033[31m", "\033[1m", "\033[0m"

# [M-03] 这两条路径原本写死成 StructureMechOne 的目录形状，而 tools/ci 是
# 三款 App 共用的一份真身。在别的项目上它们找不到文件，于是这道闸门宣布
# 「Swift 界面还没建」并退 2 —— 界面早就建好了。现在从项目自己的 ci.toml
# 读；没声明就说出这句话本身，而不是替项目编一个理由。
DEFAULT_FIGURE = "swift/Sources/StructureMechOneApp/FigureColumn.swift"
DEFAULT_EVALUATE = "swift/Sources/StructureKit/Presentation/Evaluate.swift"


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
    parser.add_argument("--figure", type=Path, default=None,
                        help="图形派发的 Swift 源；不给就读 ci.toml 的 figure_source")
    parser.add_argument("--evaluate", type=Path, default=None,
                        help="按结构画图的登记表；不给就读 ci.toml 的 evaluate_source")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    spec_path = cfg.path("canon") or (root / "spec" / "specification.json")
    if not spec_path.is_file():
        print(f"尚不适用：还没有 {spec_path.name}", file=sys.stderr)
        return 2

    figure_path = args.figure or cfg.path("figure_source")
    evaluate_path = args.evaluate or cfg.path("evaluate_source")
    if figure_path is None or evaluate_path is None:
        if cfg.source is None:
            figure_path = figure_path or (root / DEFAULT_FIGURE)
            evaluate_path = evaluate_path or (root / DEFAULT_EVALUATE)
        else:
            print("尚不适用：ci.toml 没有声明 figure_source / evaluate_source。",
                  file=sys.stderr)
            print("  这道闸门认的是 `switch module.id` + `openingFamily` 那种"
                  "集中派发的形状；一个画面一个 Drawing 视图的项目要另写一道。",
                  file=sys.stderr)
            return 2
    if not figure_path.is_file() or not evaluate_path.is_file():
        if not (root / "swift" / "Sources").is_dir():
            print("尚不适用：Swift 界面还没建（阶段 06 之前正常）",
                  file=sys.stderr)
            return 2
        where = "ci.toml 指的" if cfg.source else "（本项目没有 ci.toml，用的是模板默认）"
        print(f"✗ {where}图形源不在：")
        for path in (figure_path, evaluate_path):
            mark = "有" if path.is_file() else "不在"
            print(f"    [{mark}] {path}")
        print("  Swift 界面是建了的——路径不对，不是「尚未开始」。")
        if not cfg.source:
            print("  修法：在项目根写一份 ci.toml，声明 figure_source 与")
            print("        evaluate_source；本项目的图形不是集中派发的形状时，")
            print("        不声明它们，这道闸门会退 2 并说出那句理由。")
        return 1

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
    print(checked(len(shipping), "个出货画面"))
    if not shipping:
        print(f"  {RED}✗{OFF} 正典里一个 v1.x 模块都没有——"
              f"这不是「图形覆盖通过」，这是没检查")
        fail += 1
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
