#!/usr/bin/env python3
"""闸门 —— 正典的每一条 branching，界面上都必须有一个看得见的控件。

规范 v5.0 §5.1：`modules[].branching[].control` ——「**没有可见控件的分支
不许存在**」。事故：StructureMechOne 两处分支从未落地成画面上的选择；
Thermo 的 BR-18 分支从未被传过 nil。

多解是这一类 App 最容易让人拿到错答案而不自知的地方：程序悄悄替用户选了
一支，屏幕上没有任何东西说明它选了哪一支。**这不是显示问题，是正确性问题**
——单剪 vs 双剪差两倍，而两个数看起来一样合理。

──────────────────────────────────────────────────────────────
两级判据。第一级是本轮的硬闸门，第二级是接口。

**① 声明级（硬闸门）**

每条 `branching[]` 必须有 `control` 字段，取值属于：

    picker | toggle | segmented | parameter | display_only

前四种是「用户能改的东西」；`display_only` 是「两支都同时显示，不需要选」
（例如同屏并排给出强解与弱解）。**缺字段即未通过**——一条没有 control 的
分支，谁也说不出它在界面上长什么样，包括写它的人。

再加一条纯文本判据：`control` 声明的控件类型，要在界面源码里找得到对应的
SwiftUI 构件（`Picker` / `Toggle` / `.segmented` / `Slider`|`TextField`）。
这一条只查「这类控件在这个 App 里存在」，不查「这一条分支用的是它」——
那是第二级的事，静态分析做不到，硬要做就会变成一个乱叫的闸门。

**② 行为级（`--probe`，可选）**

真正的判据只有一个：**改变选项，读数会不会变。** 静态扫描永远答不了它。
所以这里定义一个接口，由 App 侧的探针生成器（后续工作包）产出 JSON，
本闸门只做断言。格式：

```json
{
  "app": "MechanicsOne",
  "generated": "2026-09-02T21:00:00Z",
  "branches": [
    {
      "module": "M01",
      "branch": "M01-BR1",
      "control": "picker",
      "screen": "joints",
      "options": [
        {"option": "single", "readings": {"tau": 12.5, "sigma_b": 40.0}},
        {"option": "double", "readings": {"tau": 6.25, "sigma_b": 40.0}}
      ]
    }
  ]
}
```

断言：非 `display_only` 的每条分支，**任意两个选项之间至少有一个读数不同**。
全都相同 = 这个选择器是个装饰品，用户以为自己在选，其实没有。
`readings` 里的 NaN 用 `null` 表示，`null` 与数值算「不同」，`null` 与
`null` 算「相同」——两支都算不出来的选择器同样是装饰品。

    python tools/ci/check_branching_visible.py [--root .] [--probe FILE]
                                               [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 允许的控件类型 → 界面源码里该出现的 SwiftUI 构件（正则）。
CONTROLS: dict[str, str] = {
    "picker": r"\bPicker\s*\(",
    "toggle": r"\bToggle\s*\(",
    "segmented": r"SegmentedPickerStyle|\.segmented\b",
    "parameter": r"\bSlider\s*\(|\bTextField\s*\(|\bStepper\s*\(",
    "display_only": r"",      # 不需要控件：两支同时显示
}


def shipping_modules(spec: dict) -> list[dict]:
    """出货清单。优先读 meta.ships_in_v1（正典自己的权威清单）。

    手写的「哪些模块算数」集合每一次都掉过东西（记忆里记了两次），所以
    这里的顺序是：正典明说的清单 > release 字段 > tier == core。
    """
    declared = (spec.get("meta") or {}).get("ships_in_v1")
    if declared:
        wanted = set(declared)
        return [m for m in spec["modules"] if m["id"] in wanted]
    return [m for m in spec["modules"]
            if str(m.get("release", "")).startswith("v1")
            or m.get("tier") == "core"]


def declaration_problems(modules: list[dict]) -> tuple[list[str], int]:
    """(每条问题一行, 一共看了几条 branching)。"""
    problems: list[str] = []
    total = 0
    for module in modules:
        for branch in module.get("branching") or []:
            total += 1
            bid = branch.get("id") or f"{module['id']}-?"
            control = branch.get("control")
            if control is None:
                problems.append(
                    f"{module['id']} · {bid}  没有 control 字段 —— "
                    f"「{(branch.get('question') or '')[:44]}」")
            elif control not in CONTROLS:
                problems.append(
                    f"{module['id']} · {bid}  control={control!r} 不是"
                    f" {'/'.join(CONTROLS)} 之一")
    return problems, total


def missing_widgets(modules: list[dict], app_source: str) -> list[str]:
    """声明了某类控件，而整个界面层里根本没有这类控件。"""
    wanted = {b.get("control") for m in modules for b in (m.get("branching") or [])}
    out = []
    for control in sorted(c for c in wanted if c in CONTROLS and CONTROLS[c]):
        if not re.search(CONTROLS[control], app_source):
            out.append(f"正典声明了 control={control}，"
                       f"而界面层里一个 {control} 控件都没有")
    return out


def probe_problems(probe: dict) -> tuple[list[str], int]:
    """行为级：改选项必须改读数。"""
    problems: list[str] = []
    branches = probe.get("branches") or []
    for entry in branches:
        name = f"{entry.get('module', '?')} · {entry.get('branch', '?')}"
        if entry.get("control") == "display_only":
            continue
        options = entry.get("options") or []
        if len(options) < 2:
            problems.append(f"{name}  探针只给了 {len(options)} 个选项，"
                            f"没法证明这个选择器有作用")
            continue
        readings = [opt.get("readings") or {} for opt in options]
        keys = set().union(*(set(r) for r in readings)) if readings else set()
        differs = any(
            len({json.dumps(r.get(k), sort_keys=True) for r in readings}) > 1
            for k in keys)
        if not differs:
            labels = ", ".join(str(o.get("option")) for o in options)
            problems.append(
                f"{name}  改遍每个选项（{labels}），"
                f"{len(keys)} 个读数一个都没变 —— 这个选择器是装饰品")
    return problems, len(branches)


# ──────────────────────────────── 自检 ────────────────────────────────

BAD_SPECS = [
    ("分支没有 control 字段",
     {"modules": [{"id": "M01", "release": "v1.0", "branching": [
         {"id": "M01-BR1", "question": "single or double shear?",
          "options": ["single", "double"]}]}]}),
    ("control 是个没定义的值",
     {"modules": [{"id": "M01", "release": "v1.0", "branching": [
         {"id": "M01-BR1", "control": "magic", "options": ["a", "b"]}]}]}),
]
GOOD_SPEC = {"modules": [{"id": "M01", "release": "v1.0", "branching": [
    {"id": "M01-BR1", "control": "picker", "options": ["single", "double"]}]}]}

BAD_PROBES = [
    ("改遍选项，读数一个都没变",
     {"branches": [{"module": "M01", "branch": "BR1", "control": "picker",
                    "options": [{"option": "single", "readings": {"tau": 12.5}},
                                {"option": "double", "readings": {"tau": 12.5}}]}]}),
    ("两支都算不出来（都是 null）",
     {"branches": [{"module": "M01", "branch": "BR1", "control": "picker",
                    "options": [{"option": "a", "readings": {"tau": None}},
                                {"option": "b", "readings": {"tau": None}}]}]}),
    ("只给了一个选项",
     {"branches": [{"module": "M01", "branch": "BR1", "control": "toggle",
                    "options": [{"option": "a", "readings": {"tau": 1.0}}]}]}),
]
GOOD_PROBE = {"branches": [
    {"module": "M01", "branch": "BR1", "control": "picker",
     "options": [{"option": "single", "readings": {"tau": 12.5}},
                 {"option": "double", "readings": {"tau": 6.25}}]},
    {"module": "M02", "branch": "BR2", "control": "display_only",
     "options": [{"option": "strong", "readings": {"M": 1.0}},
                 {"option": "weak", "readings": {"M": 1.0}}]},
]}


def self_test() -> int:
    ok = True
    for label, spec in BAD_SPECS:
        problems, seen = declaration_problems(shipping_modules(spec))
        good = bool(problems) and seen == 1
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  拒绝  {label}")

    problems, seen = declaration_problems(shipping_modules(GOOD_SPEC))
    good = not problems and seen == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  control=picker，声明完整")

    good = bool(missing_widgets(shipping_modules(GOOD_SPEC),
                                "struct V: View { var body: some View { Text(\"x\") } }"))
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  拒绝  声明了 picker，界面层里"
          f"一个 Picker 都没有")

    good = not missing_widgets(shipping_modules(GOOD_SPEC),
                               "Picker(\"shear\", selection: $mode) { }")
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  界面层里确实有 Picker(")

    for label, probe in BAD_PROBES:
        problems, _ = probe_problems(probe)
        good = bool(problems)
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  拒绝  探针：{label}")

    problems, seen = probe_problems(GOOD_PROBE)
    good = not problems and seen == 2
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  探针：读数真的随选项变"
          f"（display_only 那条豁免）")

    # 零对象：一份没有任何 branching 的正典不能报「全部可见」。
    empty_problems, empty_seen = declaration_problems([])
    good = empty_seen == 0 and not empty_problems
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  计数  零条 branching 时计数为 0"
          f"（由 main 判未通过）")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--probe", type=Path, default=None,
                    help="App 侧生成的行为探针 JSON（格式见 docstring）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_branching_visible.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    spec_path = cfg.path("canon") or (root / "spec" / "specification.json")
    if not spec_path.is_file():
        print("尚不适用：还没有正典（阶段 01 之前正常）", file=sys.stderr)
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    modules = shipping_modules(spec)

    app_dir = cfg.path("swift_app_dir")
    app_source = ""
    if app_dir and app_dir.is_dir():
        app_source = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                               for p in app_dir.rglob("*.swift"))

    problems, total = declaration_problems(modules)
    print(checked(total, "条 branching", f"{len(modules)} 个出货模块"))
    if total == 0:
        if not any(m.get("branching") for m in spec["modules"]):
            print("尚不适用：正典里一条 branching 都没有——这个学科可能真的"
                  "没有多解结构，但请在正典里写明，别让它是个空白。",
                  file=sys.stderr)
            return 2
        print("✗ 出货模块里一条 branching 都没数到，而正典别处有——"
              "出货清单选错了？")
        return 1

    failed = False
    if problems:
        print(f"✗ {len(problems)} / {total} 条分支没有可见控件的声明：")
        for line in problems:
            print(f"    {line}")
        print(f"  规范 v5.0 §5.1：没有可见控件的分支不许存在。"
              f"取值：{' / '.join(CONTROLS)}")
        print("  程序悄悄替用户选一支，是本类 App 最容易让人拿到错答案"
              "而不自知的地方。")
        failed = True
    else:
        print(f"✓ {total} 条分支各有 control 声明")

    if app_source:
        gaps = missing_widgets(modules, app_source)
        if gaps:
            print(f"✗ {len(gaps)} 类控件在界面层里根本不存在：")
            for line in gaps:
                print(f"    {line}")
            failed = True
        else:
            print("✓ 声明用到的每一类控件，界面层里都找得到")

    if args.probe:
        if not args.probe.is_file():
            print(f"✗ 找不到探针文件 {args.probe}")
            return 1
        probe = json.loads(args.probe.read_text(encoding="utf-8"))
        probe_bad, probed = probe_problems(probe)
        print(checked(probed, "条被探测的分支", "行为级"))
        if probed == 0:
            print("✗ 探针文件里一条分支都没有——这不是通过，这是没检查。")
            return 1
        if probe_bad:
            print(f"✗ {len(probe_bad)} 条分支改了选项而读数不变：")
            for line in probe_bad:
                print(f"    {line}")
            failed = True
        else:
            print(f"✓ {probed} 条分支的读数都随选项改变")
    else:
        print("  （行为级未跑：没给 --probe。静态扫描证明不了"
              "「改选项读数会变」，那要 App 侧的探针。）")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
