#!/usr/bin/env python3
"""Gate 06 —— 正典里的每一条 LaTeX 命令，渲染器都必须认识。

    python check_formula_coverage.py spec/specification.json --python python/src

界面上显示公式是阶段 06 的护城河之一，也是法律隔离的支点：**公式本身可以
显示，书名不可以**。但公式只有在渲染正确时才是这个作用。

一个不认识的命令不会报错，它会把反斜杠原样打到屏幕上——而在斜体衬线字体
里，一个反斜杠看起来就像竖线，在力学里那是范数、绝对值或者行列式。
**没被处理的命令看起来不像缺陷，看起来像另一个公式。**

所以这道闸门做两件事：
  1. 抽出正典全部 formula_display 里的每一条命令，逐条对照渲染器的表；
  2. 渲染全部公式，检查结果里不再有反斜杠。

第二条不能省。第一条只证明命令在表里，不证明它被正确地用了——`\\le` 曾经
排在 `\\left` 前面被替换，于是每一个 `\\left(` 都变成了 `≤ft(`，而两张表
都是齐全的。
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

TOKEN = re.compile(r"\\[A-Za-z]+|\\.")


def main() -> int:
    ap = argparse.ArgumentParser()
    # [M-03] `canon` was positional-required and the renderer was imported as
    # the literal `mechanicskit.ui.latex`. tools/ci is one shared body shared by
    # three apps: on the others this crashed or, worse, was written off in the
    # runner as "not applicable, formulas render fine" -- a hand-written reason
    # that the script, run by hand, contradicted with ten real hits.
    ap.add_argument("canon", nargs="?", type=Path, default=None)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--python", type=Path, default=None)
    ap.add_argument("--latex-module", default=None,
                    help="渲染器模块，如 mechanicskit.ui.latex；"
                         "不给就读 ci.toml 的 latex_module")
    args = ap.parse_args()

    cfg = load_config(args.root)
    canon_path = args.canon or cfg.path("canon")
    if canon_path is None or not canon_path.is_file():
        print("尚不适用：还没有正典（阶段 01 之前正常）", file=sys.stderr)
        return 2
    src = args.python or cfg.path("python_src_dir")
    module_name = args.latex_module or cfg.get("latex_module")
    if src is None or module_name is None:
        print("尚不适用：ci.toml 没有声明 latex_module（或 python_src_dir）——"
              "本项目的公式渲染器不在这道闸门认得的位置。", file=sys.stderr)
        print("  声明了它这道闸门才有意义：它比对的是【本 App 正典里的公式】"
              "和【本 App 渲染器的命令表】。", file=sys.stderr)
        return 2
    sys.path.insert(0, str(src.resolve()))
    try:
        latex = importlib.import_module(module_name)
    except ImportError as error:
        print(f"✗ 导入渲染器 {module_name} 失败：{error}")
        print(f"  PYTHONPATH 里加的是 {src}")
        return 1
    COMMANDS, STRUCTURAL, render = (latex.COMMANDS, latex.STRUCTURAL,
                                    latex.render)

    canon = json.loads(canon_path.read_text(encoding="utf-8"))
    known = {command for command, _ in COMMANDS} | set(STRUCTURAL)

    unknown: dict[str, list[str]] = {}
    residue: list[tuple[str, str]] = []
    empty: list[str] = []

    for module in canon["modules"]:
        source = module.get("formula_display", "")
        if not source.strip():
            empty.append(module["id"])
            continue
        for token in TOKEN.findall(source):
            if token not in known:
                unknown.setdefault(token, []).append(module["id"])
        rendered = render(source)
        if "\\" in rendered:
            residue.append((module["id"], rendered))

    failed = False
    if empty:
        print(f"✗ {len(empty)} 个 module 没有 formula_display：{empty}")
        failed = True
    if unknown:
        print(f"✗ {len(unknown)} 条命令渲染器不认识：")
        for token, modules in sorted(unknown.items()):
            print(f"    {token!r}  出现在 {', '.join(sorted(set(modules))[:6])}")
        failed = True
    if residue:
        print(f"✗ {len(residue)} 条公式渲染后仍带反斜杠：")
        for module_id, text in residue[:8]:
            print(f"    {module_id}: {text}")
        failed = True

    total = len(canon["modules"])
    print(checked(total, "条 formula_display",
                  f"渲染器 {module_name}"))
    if total == 0:
        print("✗ 正典里一个 module 都没有——这不是「全部可渲染」，这是没检查。")
        return 1
    if failed:
        print(f"\n  渲染器的表在 {module_name.replace('.', '/')}.py，"
              "Swift 侧在 Presentation/Latex.swift，两侧必须同时改。")
        return 1

    print(f"✓ 正典 {total} 条公式全部可渲染，无未知命令、无残留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
