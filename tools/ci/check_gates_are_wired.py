#!/usr/bin/env python3
"""闸门 —— 每一个 check_* 脚本都必须真的被某个 runner 调用。

写这道检查的理由是一件已经发生的事：`check_sufficiency.py` ——
**规范里 Gate 02 的核心实现**、七条充分性判据 —— 在本项目的套件里根本没有
被调用过。模板的通用 runner 调了它，但它假设扁平的目录布局，于是永远返回
「尚不适用」，在日志里显示为一行黄色的「跳过」。

接上之后，七条里四条不满足。**也就是说，整个阶段 02 到阶段 09 期间，
「验证是否充分」这个问题从来没有被问过，而每一次跑套件都显示全绿。**

一个不存在的闸门，人会记得它不存在。一个存在、但没有被任何东西调用的闸门，
比不存在更糟：仓库里有它的源码、文档里有它的名字、判例集里有它的编号，
**每一样都在暗示这件事已经查过了。**

规则很简单，也刻意粗糙：

    tools/ci/check_*.{py,sh} 里的每一个脚本，
    必须在某个 run_*.sh 里出现。

出现的方式有两种，都算：
  * 被调用 —— 正常情形；
  * 出现在一行 `pending` 里 —— 本阶段还到不了（截图、线上 URL）。
    **必须写在 runner 里**，因为那是跑套件的人会看到的地方；
    写在别处等于没写。

不区分「调用」和「pending」是有意的：这道检查要保证的是**有人做过决定并把
它写在了 runner 里**，而不是替人判断那个决定对不对。

    python tools/ci/check_gates_are_wired.py [--root .] [--self-test]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: 不是闸门的东西：生成器、剥离器、渲染器、runner 自己。
#: 判据是**名字的前缀**，不是一份清单——清单会漂。
NOT_A_GATE = ("make_", "strip_", "render_", "run_", "audit_", "emit_", "build_")


def gate_scripts(ci: Path) -> list[Path]:
    return sorted(p for p in ci.iterdir()
                  if p.is_file() and p.name.startswith("check_")
                  and p.suffix in (".py", ".sh")
                  and not p.name.startswith(NOT_A_GATE))


def runners(root: Path) -> list[Path]:
    found: list[Path] = []
    for directory in (root / "tools" / "ci", root / "tools" / "build"):
        if directory.is_dir():
            found += sorted(directory.glob("run_*.sh"))
    return found


def ci_runners(root: Path) -> list[str]:
    """The runner scripts CI actually invokes, read from the workflow.

    Read rather than assumed: hard-coding "run_all.sh" would make this check
    silently wrong on the next project that names its runner something else,
    and a check that is silently wrong is the thing this file exists to stop.
    """
    names: set[str] = set()
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        for flow in sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml")):
            text = flow.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"(run_[A-Za-z0-9_]*\.sh)", text):
                names.add(match.group(1))
    return sorted(names)


def wiring(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """哪些闸门被哪些 runner 提到了，以及一个都没提到的。"""
    ci = root / "tools" / "ci"
    if not ci.is_dir():
        return {}, []
    texts = {r.name: r.read_text(encoding="utf-8", errors="ignore")
             for r in runners(root)}
    # **Which runner** matters, not merely that some runner mentions the gate.
    #
    # This check used to accept any `run_*.sh` as evidence of wiring.  One gate
    # was named only by a stale partial runner that CI does not invoke, so it
    # counted as wired and had never executed once -- failing wholesale the
    # first time anybody ran it by hand.  "Referenced by a runner" and "runs in
    # CI" are different claims, and only the second one is worth anything.
    live = set(ci_runners(root))
    if not live:                       # no workflow to read: fall back, loudly
        live = set(texts)
    seen: dict[str, list[str]] = {}
    orphans: list[str] = []
    for gate in gate_scripts(ci):
        where = [name for name, text in texts.items()
                 if gate.name in text and name in live]
        if where:
            seen[gate.name] = where
        else:
            orphans.append(gate.name)
    return seen, orphans


SELF_TEST = [
    ("被调用的闸门", "step 'x' python3 tools/ci/check_thing.py", "check_thing.py", True),
    ("声明 pending 的闸门", "pending 'Gate 07' check_shots.py '尚未到达'",
     "check_shots.py", True),
    ("一个都没提到的闸门", "step 'y' python3 tools/ci/check_other.py",
     "check_thing.py", False),
]


def self_test() -> int:
    """交给它三个已知样本：两个必须放行，一个必须抓到。"""
    ok = True
    for label, runner_text, gate_name, should_pass in SELF_TEST:
        mentioned = gate_name in runner_text
        good = mentioned == should_pass
        ok &= good
        verdict = "放行" if should_pass else "抓到"
        print(f"  {'PASS' if good else 'FAIL'}  {verdict}  {label}")

    # 前缀过滤必须真的排除生成器，否则这道闸门会对着 make_input_matrix.py 报警
    excluded = [n for n in ("make_input_matrix.py", "strip_spec.py",
                            "run_all_local.sh", "render_source_page.py")
                if n.startswith(NOT_A_GATE) or not n.startswith("check_")]
    good = len(excluded) == 4
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  生成器与 runner 不算闸门")
    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_gates_are_wired.py 自检")
        return self_test()

    seen, orphans = wiring(args.root.resolve())
    if not seen and not orphans:
        print("尚不适用：没有 tools/ci/", file=sys.stderr)
        return 2
    if orphans:
        print(f"✗ {len(orphans)} 道闸门没有被任何 runner 调用：")
        for name in orphans:
            print(f"    {name}")
        print("  一道存在但没人调用的闸门，比不存在更糟——"
              "源码、文档、判例集都在暗示这件事已经查过了。")
        print("  要么接进某个 run_*.sh，要么在那里写一行 pending 说明为什么还到不了。")
        return 1
    print(f"✓ {len(seen)} 道闸门全部被 runner 提到")
    return 0


if __name__ == "__main__":
    sys.exit(main())
