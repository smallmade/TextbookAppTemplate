#!/usr/bin/env python3
"""Gate: every layer-3 symbolic proof actually gets run.

Layers 1, 2, 4 and 5 all compare numbers, and a wrong number stands out
against a right one. Layer 3 compares an *equation to itself* -- it proves
that a closed form shipped in the kernel is really the solution to the
equation the textbook claims it solves, not just a number that happens to sit
close to the right answer. A wrong symbolic proof is indistinguishable from a
right one by its exit code alone: sympy will simplify a mis-transcribed
identity to ``0 == 0`` just as happily as a correct one, and the difference
only shows up if a human reads the algebra.

That makes this gate narrow by design: it does not re-derive anything, and it
cannot tell a sound proof from an unsound one. All it checks is that the
proof scripts under ``data/layer3-symbolic/`` are actually *executed*, which
until this gate existed, nothing was doing. One of them sat in the repository
for an unknown number of sessions with its docstring claiming "exits non-zero
if any identity fails" while its newest block computed a value and discarded
it without ever asserting anything -- a script that runs clean forever
because it never checks anything is the same failure this project's own
``check_gates_are_wired.py`` names: **a check that cannot go red is worse
than no check**, because the source, the docstring and the ledger all imply
it was verified.

Each ``verify_*.py`` is a standalone script -- no pytest decorators, run
directly, prints nothing and exits non-zero on the first failed identity
(matching the convention the layer-3 scripts already use). This gate globs
for them rather than listing them by hand, for the same reason
``check_port_coverage.py`` insists on automatic discovery over a hand-written
tuple: a hand-written list is a thing the next module's author forgets to
update, and a forgotten entry reports "layer 3 complete" while covering one
module fewer than it did yesterday.

    python3 tools/ci/check_layer3_symbolic.py [--root .] [--self-test]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

LAYER_DIR = Path("python") / "tests" / "data" / "layer3-symbolic"


def discover(root: Path) -> list[Path]:
    directory = root / LAYER_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("verify_*.py"))


def run_one(script: Path) -> tuple[bool, str]:
    result = subprocess.run([sys.executable, str(script)],
                            capture_output=True, text=True, check=False)
    return result.returncode == 0, result.stderr


def check(root: Path) -> int:
    directory = root / LAYER_DIR
    if not directory.is_dir():
        print(f"尚不适用：没有 {LAYER_DIR}", file=sys.stderr)
        return 2

    scripts = discover(root)
    if not scripts:
        print(f"✗ {LAYER_DIR} 存在，但一个 verify_*.py 都没有 —— "
              "一层不执行任何东西的验证，比没有这一层更糟")
        return 1

    failed: list[tuple[Path, str]] = []
    for script in scripts:
        ok, stderr = run_one(script)
        mark = "✓" if ok else "✗"
        print(f"  {mark} {script.relative_to(root)}")
        if not ok:
            failed.append((script, stderr))

    if failed:
        print(f"\n✗ {len(failed)}/{len(scripts)} 个层 3 证明未通过：")
        for script, stderr in failed:
            print(f"    {script.name}:")
            for line in stderr.strip().splitlines()[-5:]:
                print(f"      {line}")
        return 1

    print(f"\n✓ {len(scripts)} 个层 3 证明全部被执行，全部通过")
    return 0


def self_test() -> int:
    """Two known-bad samples and one known-good, all in an isolated tempdir.

    The real ``data/layer3-symbolic/`` must never be used for the bad
    samples: writing a script there that is *supposed* to fail would leave a
    permanently red gate in the actual project the moment this file is
    imported anywhere real.
    """
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        directory = root / LAYER_DIR
        directory.mkdir(parents=True)

        # 空目录：一个 verify_*.py 都没有，必须被抓。
        caught = check(root) != 0
        print(f"  {'PASS' if caught else 'FAIL'}  拒绝  层目录存在但没有脚本")
        ok &= caught

        # 一个已知会失败的脚本：必须被抓，而不是被 subprocess 的返回码之外的
        # 任何东西掩盖（比如误判 stdout 而不是 returncode）。
        (directory / "verify_broken.py").write_text(
            "import sys\nassert 1 == 2, 'deliberately false'\nsys.exit(1)\n")
        caught = check(root) != 0
        print(f"  {'PASS' if caught else 'FAIL'}  拒绝  一个已知会失败的证明")
        ok &= caught

        # 换成一个已知会通过的脚本：必须放行，证明上面的红不是因为跑不起来
        # 任何脚本,而确实是在读 returncode。
        (directory / "verify_broken.py").write_text(
            "import sys\nassert 1 == 1\nsys.exit(0)\n")
        quiet = check(root) == 0
        print(f"  {'PASS' if quiet else 'FAIL'}  放行  一个已知会通过的证明")
        ok &= quiet

    # 目录本身不存在：Gate 04 那种「尚不适用」，不是失败，但也不是静默的 0。
    with tempfile.TemporaryDirectory() as tmp:
        code = check(Path(tmp))
        matches = code == 2
        print(f"  {'PASS' if matches else 'FAIL'}  区分  目录不存在 vs 目录为空")
        ok &= matches

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败——闸门不会报警")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_layer3_symbolic.py 自检")
        return self_test()

    return check(args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())
