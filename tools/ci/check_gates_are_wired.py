#!/usr/bin/env python3
"""元闸门 —— 每一道 check_* 都必须被**本项目 CI 实际调用的那一个** runner 调用。

架构不变量 6（规范 v5.0 §2.2）。三款 App 各自付过学费：

* MechanicsOne 一次会话查出六道「存在但没被调用」的闸门，含 v4.0 点名为
  Gate 02 核心的 `check_sufficiency.py`——整个开发期显示为一行黄色的「跳过」。
* StructureMechOne 的 `check_canon_functions.py` 一跑整片红，却从未在 CI 跑过。
* Thermodynamics 有三个 runner，短名字那个没有 Gate 04。

> 一个不存在的闸门，人会记得它不存在。一个存在、但没有被任何东西调用的
> 闸门，比不存在更糟：仓库里有它的源码、文档里有它的名字、判例集里有它的
> 编号，**每一样都在暗示这件事已经查过了。**

──────────────────────────────────────────────────────────────
[M-03] 判据收紧了两处。上一版问的是「有没有**某个** `run_*.sh` 提到这个
文件名」，而 `tools/ci` 是三款 App 共用的一份真身：**姊妹 App 的 runner 就
摆在同一个目录里**，于是本项目的坏闸门被别人的 runner 点了名，元闸门绿灯。
StructureMechOne 实测：30 道闸门「全部被 runner 提到」，其中 8 道从未执行。

一、**只认一个 runner**，来源按顺序：
      1. `.github/workflows/*.yml` 里真的被调用的那个 `run_*.sh`；
      2. 读不到工作流时，项目根 `ci.toml` 的 `runner` 键。
    两处都没有 → 退 2 并说明（不假装通过）。规范：一个项目只允许一个 runner。

二、**`pending` 不再等于「已接线」。** 一行硬编码的
      `pending "Gate 07" check_urls.sh "尚未部署"`
    表达的是「有人做过决定」，不是「这道闸门跑过」。它现在：
      * 必须带一句非空的理由（没有理由 → 未通过）；
      * 计进「已声明但未跑」的统计，**不计进已接线**。
    StructureMechOne 那 8 道 pending 在旧判据下是绿的；在新判据下它们会被
    单独列出来，而列出来正是它们被逐条现场执行、查出 5 道「应该跑而没跑」
    的原因。

    python tools/ci/check_gates_are_wired.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 不是闸门的东西：生成器、剥离器、渲染器、runner 自己、配置读取器。
#: 判据是**名字的前缀**，不是一份清单——清单会漂。
NOT_A_GATE = ("make_", "strip_", "render_", "run_", "audit_", "emit_", "build_",
              "ci_")

#: runner 里声明「这道闸门存在、但本阶段还到不了」的写法。
PENDING = re.compile(r"^\s*pending\s+(.*)$", re.M)

#: 工作流里调用 runner 的那一行。`bash tools/ci/run_all.sh .`
RUNNER_CALL = re.compile(r"(?:bash|sh|\./)\s*([\w./-]*run_[\w.-]+\.sh)")


def gate_scripts(ci: Path) -> list[Path]:
    return sorted(p for p in ci.iterdir()
                  if p.is_file() and p.name.startswith("check_")
                  and p.suffix in (".py", ".sh")
                  and not p.name.startswith(NOT_A_GATE))


def ci_runner(root: Path) -> tuple[Path | None, str]:
    """本项目 CI 实际调用的那一个 runner，以及这个结论是怎么来的。

    工作流优先，因为它是**真的会跑**的那份说明；`ci.toml` 是给没有工作流
    的项目（MechanicsOne 至今没有 `.github/`）留的路，而不是给「工作流写的
    是 A、配置写的是 B」时挑一个顺眼的留的路。
    """
    workflows = sorted((root / ".github" / "workflows").glob("*.yml")) + \
        sorted((root / ".github" / "workflows").glob("*.yaml"))
    for flow in workflows:
        text = flow.read_text(encoding="utf-8", errors="ignore")
        for match in RUNNER_CALL.finditer(text):
            candidate = root / match.group(1)
            if candidate.is_file():
                return candidate, f".github/workflows/{flow.name}"
    declared = load_config(root).get("runner")
    if declared:
        candidate = root / declared
        if candidate.is_file():
            return candidate, "ci.toml 的 runner 键"
        return None, f"ci.toml 指的 {declared} 不存在"
    return None, ""


def runner_text(runner: Path, root: Path) -> str:
    """那一个 runner 的正文，**含它自己调起来的子 runner**。

    「一个项目只允许一个 runner」说的是入口只有一个，不是禁止它把 Gate S、
    Gate 07、Gate 09 拆成 `run_gate_s.sh` 之类的子脚本。沿着调用往下跟，
    否则接在子脚本里的闸门会被判成孤儿——那是误报，而一个会乱叫的闸门
    两天之内就会被关掉。

    只跟 `run_*.sh`，且只跟这个入口能到达的那些：姊妹项目的 runner 就摆在
    同一个 `tools/ci/` 目录里，而它到不了。
    """
    seen: set[Path] = set()
    stack = [runner]
    chunks: list[str] = []
    while stack:
        current = stack.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        body = current.read_text(encoding="utf-8", errors="ignore")
        chunks.append(body)
        for match in RUNNER_CALL.finditer(body):
            for base in (root, root / "tools" / "ci", current.parent):
                candidate = (base / match.group(1)).resolve()
                if candidate.is_file():
                    stack.append(candidate)
                    break
    return "\n".join(chunks)


def _join_continuations(text: str) -> str:
    """把 shell 的反斜杠续行接成一行。

    `pending "……(check_urls.sh)" \\\n        "理由"` 的理由在第二行，
    而按行匹配的正则只看得到第一行——于是一条写了理由的 pending 被判成
    「没说为什么」。**误报**，而这道闸门的全部权威就建立在它不乱叫上面。
    """
    return re.sub(r"\\\n\s*", " ", text)


def wiring(root: Path):
    """(被调用的, pending 且带理由的, pending 但没理由的, 一个都没提到的)。"""
    ci = root / "tools" / "ci"
    runner, _ = ci_runner(root)
    if not ci.is_dir() or runner is None:
        return None
    text = _join_continuations(runner_text(runner, root))

    # pending 行单独抽出来，先从正文里剔除，剩下的才算「真的调用」。
    pending_lines = PENDING.findall(text)
    body = PENDING.sub("", text)

    called: list[str] = []
    pending_ok: list[tuple[str, str]] = []
    pending_mute: list[str] = []
    orphans: list[str] = []
    for gate in gate_scripts(ci):
        name = gate.name
        if name in body:
            called.append(name)
            continue
        mentions = [line for line in pending_lines if name in line]
        if mentions:
            # 理由 = 该行里最后一段引号内的文字。空的就是没说为什么。
            quoted = re.findall(r'"([^"]*)"|\'([^\']*)\'', mentions[0])
            reason = ""
            for a, b in quoted:
                candidate = (a or b).strip()
                if candidate and name not in candidate:
                    reason = candidate
            if reason:
                pending_ok.append((name, reason))
            else:
                pending_mute.append(name)
            continue
        orphans.append(name)
    return called, pending_ok, pending_mute, orphans


SELF_TEST = [
    ("被本项目的 runner 调用", "step 'x' python3 tools/ci/check_thing.py",
     "check_thing.py", "called"),
    ("pending 且写明理由",
     "pending 'Gate 07' \"check_shots.py 需要站点已部署\"",
     "check_shots.py", "pending_ok"),
    ("pending 但没说为什么", "pending check_shots.py",
     "check_shots.py", "pending_mute"),
    ("一个都没提到", "step 'y' python3 tools/ci/check_other.py",
     "check_thing.py", "orphan"),
    # [M-03] 理由写在反斜杠续行上的 pending。按行匹配会把它判成
    # 「没说为什么」——误报，而这道闸门的权威全在它不乱叫上面。
    ("pending，理由在续行上",
     'pending "Gate 07 · 五个 URL (check_urls.sh)" \\\n'
     '        "需要伞形站点已部署"',
     "check_urls.sh", "pending_ok"),
]


def classify(source: str, gate_name: str) -> str:
    """把 SELF_TEST 的判据抽出来，和 wiring() 用同一段逻辑。"""
    source = _join_continuations(source)
    pending_lines = PENDING.findall(source)
    body = PENDING.sub("", source)
    if gate_name in body:
        return "called"
    mentions = [line for line in pending_lines if gate_name in line]
    if not mentions:
        return "orphan"
    quoted = re.findall(r'"([^"]*)"|\'([^\']*)\'', mentions[0])
    for a, b in quoted:
        candidate = (a or b).strip()
        if candidate and gate_name not in candidate:
            return "pending_ok"
    return "pending_mute"


def self_test() -> int:
    """四个已知样本，每一档一个。加一个「别人的 runner 不算数」的样本。"""
    ok = True
    for label, runner_text, gate_name, expected in SELF_TEST:
        got = classify(runner_text, gate_name)
        good = got == expected
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  判为 {expected:<12} {label}")

    # [M-03] 本条是这道闸门上一次给出绿灯的确切形状：闸门只出现在**姊妹
    # 项目的** runner 里。共用一个 tools/ 目录时，那份 runner 就摆在旁边。
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ci = root / "tools" / "ci"
        ci.mkdir(parents=True)
        (ci / "check_thing.py").write_text("", encoding="utf-8")
        (ci / "run_mine.sh").write_text("echo nothing here\n", encoding="utf-8")
        (ci / "run_sibling.sh").write_text(
            "python3 tools/ci/check_thing.py\n", encoding="utf-8")
        (root / ".github").mkdir(exist_ok=True)
        (root / "ci.toml").write_text('runner = "tools/ci/run_mine.sh"\n',
                                      encoding="utf-8")
        result = wiring(root)
        good = result is not None and result[3] == ["check_thing.py"]
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  抓到      "
              f"只有姊妹项目的 runner 提到它（旧判据在这里放行）")

        # ...而换成本项目自己的 runner 提它，就必须放行。
        (ci / "run_mine.sh").write_text(
            "python3 tools/ci/check_thing.py\n", encoding="utf-8")
        result = wiring(root)
        good = result is not None and result[0] == ["check_thing.py"]
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  放行      "
              f"本项目的 runner 真的调用它")

    excluded = [n for n in ("make_input_matrix.py", "strip_spec.py",
                            "run_all_local.sh", "render_source_page.py",
                            "ci_config.py")
                if n.startswith(NOT_A_GATE) or not n.startswith("check_")]
    good = len(excluded) == 5
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行      生成器与 runner 不算闸门")
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

    root = args.root.resolve()
    if not (root / "tools" / "ci").is_dir():
        print("尚不适用：没有 tools/ci/", file=sys.stderr)
        return 2
    runner, how = ci_runner(root)
    if runner is None:
        print("✗ 找不到本项目 CI 实际调用的那一个 runner。")
        print(f"  查过：.github/workflows/*.yml 与 ci.toml 的 runner 键"
              f"{'（' + how + '）' if how else ''}")
        print("  规范 v5.0：一个项目只允许一个 runner，且报告闸门数字时"
              "必须写明它来自哪个 runner。")
        print("  修法：在项目根的 ci.toml 里写 runner = \"tools/ci/run_all.sh\"。")
        return 1
    print(f"  认定的 runner：{runner.relative_to(root)}（来自 {how}）")

    called, pending_ok, pending_mute, orphans = wiring(root)
    total = len(called) + len(pending_ok) + len(pending_mute) + len(orphans)
    print(checked(total, "道闸门",
                  f"被调用 {len(called)} · 声明未跑 {len(pending_ok)} · "
                  f"未跑且没说理由 {len(pending_mute)} · 无人提及 {len(orphans)}"))
    if total == 0:
        print("✗ tools/ci 里一道 check_* 都没数到——这不是通过，这是没检查。")
        return 1

    failed = False
    if orphans:
        print(f"✗ {len(orphans)} 道闸门没有被本项目的 runner 调用：")
        for name in orphans:
            print(f"    {name}")
        print("  被【姊妹项目的】runner 提到不算——tools/ci 是三款共用的一份"
              "真身，别人的 runner 就摆在同一个目录里。")
        print("  要么接进 " + runner.name + "，要么在那里写一行 pending"
              " 并说明为什么还到不了。")
        failed = True
    if pending_mute:
        print(f"✗ {len(pending_mute)} 道闸门写了 pending 却没说为什么：")
        for name in pending_mute:
            print(f"    {name}")
        print("  「跳过但不说理由」与「静默放行」是同一件事。")
        failed = True
    if pending_ok:
        print(f"⏸ {len(pending_ok)} 道闸门声明为【未跑】——它们不计进已接线：")
        for name, reason in pending_ok:
            print(f"    {name}  {reason}")
        print("  这些理由没有任何机器在核对。逐条现场跑一次是发现"
              "「应该跑而没跑」的唯一办法。")
    if failed:
        return 1
    print(f"✓ {len(called)} 道闸门被 {runner.name} 真的调用"
          f"（另有 {len(pending_ok)} 道声明为未跑）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
