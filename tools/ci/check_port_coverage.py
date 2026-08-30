#!/usr/bin/env python3
"""Gate 05 —— 对等测试：Python 每个公开函数在 Swift 侧是否存在。

    python check_port_coverage.py --python src/pkg --swift swift/Sources/Core

只比对名字，不比对正确性（正确性由 conformance fixture 负责）。它专抓一种
反复发生、且对所有 fixture 隐形的失败：**一个函数存在于一边、单纯不存在
于另一边。没有人写的 fixture，比较的是零。**

这个项目被同一件事咬过两次：一次是手写元组漏了两个模块，报告照样显示
「79/79 已移植」；一次更糟——composition 层三个模块在 Swift 侧完全不存在，
十一个公开函数既没被计数也没被搬过去，因为没有东西在看 kernel 以上的层。

所以：清单一律**自动探索**，禁止手写白名单；受检层五个，缺一不可。
"""

import argparse
import ast
import re
import sys
from pathlib import Path

# 必须跨越语言边界的层，缺一不可。第二次事故就发生在 composition。
CROSSING = ("kernel", "composition", "solve", "ui", "dimension")


def python_public_names(layer_dir: Path) -> set[str]:
    """自动探索，不是手写白名单——这正是第一次事故的病根。"""
    names: set[str] = set()
    for py in layer_dir.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    names.add(node.name)
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                names.add(node.name)
    return names


def swift_source_text(swift_dir: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                     for p in swift_dir.rglob("*.swift"))


def to_camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(w.capitalize() for w in rest)


def swift_identifiers(text: str) -> set[str]:
    """Every identifier in the Swift sources, lowercased.

    Used for the acronym comparison below, which needs to know what names exist
    rather than whether one substring appears.
    """
    return {word.lower() for word in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", text)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", required=True, type=Path)
    ap.add_argument("--swift", required=True, type=Path)
    args = ap.parse_args()

    swift_text = swift_source_text(args.swift)
    identifiers = swift_identifiers(swift_text)
    missing_layers, missing_names, total = [], [], 0

    for layer in CROSSING:
        pdir = args.python / layer
        if not pdir.is_dir():
            missing_layers.append(layer)
            continue
        for name in sorted(python_public_names(pdir)):
            total += 1
            camel = to_camel(name)
            if re.search(rf"\b({re.escape(name)}|{re.escape(camel)})\b", swift_text):
                continue
            # Swift spells acronyms uniformly -- `shearFromUDL`, not
            # `shearFromUdl`; `memberLength2D`, not `memberLength2d`. The camel
            # rule above cannot produce those, and demanding it would make this
            # gate require unidiomatic Swift, which is how a gate gets turned
            # off. Compare case-insensitively against the identifiers that are
            # actually there: the question is whether the name **exists**, not
            # how it is capitalised.
            if camel.lower() in identifiers:
                continue
            missing_names.append(f"{layer}.{name}")

    if missing_layers:
        print(f"✗ 受检层缺失：{missing_layers}")
        print("  CROSSING 必须列出全部五层——第二次事故就发生在没人看的那一层")
    if missing_names:
        print(f"✗ {len(missing_names)} / {total} 个公开名在 Swift 侧找不到：")
        for n in missing_names[:40]:
            print(f"    {n}")
        if len(missing_names) > 40:
            print(f"    …… 另有 {len(missing_names) - 40} 个")

    if missing_layers or missing_names:
        return 1
    print(f"✓ 对等测试通过：{total} 个公开名，五层全覆盖")
    return 0


if __name__ == "__main__":
    sys.exit(main())
