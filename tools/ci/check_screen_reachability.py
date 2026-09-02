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

`--release` 决定检查到哪一档：默认只看 `v1.0`，`--release v1.1` 把 v1.1 的
模块也纳进来。**在 `--release` 明确点名的那一档里，`partial` 也失败**——
因为一个模块的界面「做了一半」正是本仓库反复发生的事，只报告不失败等于
没有闸门。

一个模块可以在正典里写 `ui_deferred: "<理由>"` 免于这一条。但**免除会自检**：
被标了 `ui_deferred` 的模块如果其实**全部输出都到得了**，闸门失败并要求把
那行标记删掉。**一条过期的豁免和一条真的豁免，在日志里必须分得开。**

    python tools/ci/check_screen_reachability.py [--root .] [--release v1.0|v1.1]
                                                 [--write] [--self-test]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.S)
COMMENT_LINE = re.compile(r"//[^\n]*")

#: [A-12] Verified false positives -- the screen does show this quantity, but
#: through a route more general than the specific closed form the canon
#: originally pointed at.  Each was checked by hand: found the property that
#: actually feeds the on-screen Readout, and confirmed it computes the same
#: physical quantity by a broader method.  A miss NOT in this table is a real
#: gap; one that is gets a reason printed instead of a bare accusation.
#:
#: Keyed by (module id, symbol) so a module can have both exempted and
#: genuinely missing outputs without either hiding the other.
EXEMPT: dict[tuple[str, str], str] = {
    ("M21", "M_fix_a"):
        "BeamSession.fixedMoment reads the general solver's own reactions "
        "for whatever loads are configured, rather than evaluating the "
        "single-uniform-load closed form the canon named -- the closed form "
        "is one point the general solver already covers.",
    ("M21", "M_fix_b"):
        "Same solver, same reason: the single-point-load closed form is "
        "another point the general solution already covers.",
    ("M22", "sigma_max"):
        "BendingSession.stressTop/stressBottom each evaluate the general "
        "flexure formula at the section's own two extreme-fibre coordinates, "
        "which is correct for an unsymmetric section and the closed form "
        "(one shared c) is not.",
    ("M27", "tau_max"):
        "ShearStressScreen takes the peak of the scanned shear-through-depth "
        "profile, which is right for an arbitrary built-up section; the "
        "closed form only holds for a plain rectangle.",
}
#
# Removed 2026-08-31: ("M46", "K_eff"). It was true when written -- the screen
# only had a continuous K slider, so the four-named-conditions closed form was
# never called. Then the Columns screen grew a readout that calls it, and the
# entry became a lie nobody was checking. `stale_exemptions` now catches
# exactly that, and caught this one.
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


#: Releases in order. ``--release v1.1`` means "v1.0 and v1.1", not "v1.1 only":
#: a v1.1 check that quietly stopped covering v1.0 would be a worse gate than
#: the one it replaced.
RELEASES: tuple[str, ...] = ("v1.0", "v1.1")


def in_release(module: dict, upto: str) -> bool:
    """Is this module part of the release being checked?

    ``tier == "core"`` still counts, regardless of the release label: that is
    how the gate behaved before ``--release`` existed, and a module promoted to
    core is by definition shipping.
    """
    if module.get("tier") == "core":
        return True
    release = module.get("release")
    if release not in RELEASES:
        return False
    return RELEASES.index(release) <= RELEASES.index(upto)


def classify(spec: dict, seen: set[str],
             upto: str = "v1.0") -> list[tuple[str, str, list[str], list[str]]]:
    rows = []
    for module in spec["modules"]:
        if not in_release(module, upto):
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


def split_exempted(
        partial: list[tuple[str, str, list[str]]]
) -> tuple[list[tuple[str, str]], list[tuple[str, str, list[str]]]]:
    """[A-12] ``(exempted (mid, sym) pairs, the real misses that remain)``."""
    exempted = [(mid, sym) for mid, _, missing in partial for sym in missing
               if (mid, sym) in EXEMPT]
    real = [(mid, title, [s for s in missing if (mid, s) not in EXEMPT])
           for mid, title, missing in partial]
    return exempted, [(mid, title, missing) for mid, title, missing in real
                      if missing]


def stale_exemptions(rows) -> list[tuple[str, str]]:
    """EXEMPT pairs whose symbol is now genuinely reachable.

    The same rot `split_deferred` guards against, in the older table. An EXEMPT
    entry says "the screen shows this by a more general route, so the specific
    closed form never gets called". The day someone adds a Readout that *does*
    call it, the entry stops being true -- and nothing was watching. It happened
    on the first try: M46.K_eff went stale the moment the Columns screen grew a
    K_eff readout, and only a hand check noticed.
    """
    reached = {(mid, sym) for mid, _, arrived, _ in rows for sym in arrived}
    return sorted(pair for pair in EXEMPT if pair in reached)


def split_deferred(
        partial: list[tuple[str, str, list[str]]],
        full: list[str],
        deferred: dict[str, str],
) -> tuple[list[tuple[str, str, list[str], str]], list[tuple[str, str, list[str]]],
           list[str]]:
    """Separate canon-declared UI deferrals from real gaps, and catch stale ones.

    Returns ``(deferred rows, real gaps, stale markers)``.

    A ``ui_deferred`` module whose outputs are **all** reachable is a stale
    marker: the work got done and nobody deleted the excuse. It is returned
    separately and fails the gate, because an exemption nobody re-checks is how
    a gate stops meaning anything.
    """
    held = [(mid, title, missing, deferred[mid])
            for mid, title, missing in partial if mid in deferred]
    real = [(mid, title, missing) for mid, title, missing in partial
            if mid not in deferred]
    stale = sorted(mid for mid in deferred if mid in full)
    return held, real, stale


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

    # [A-12] A known-exempt pair must be filtered out; an unlisted symbol in
    # the same module must survive, so a real new gap cannot hide beside a
    # verified old one.
    exempted, real = split_exempted([("M27", "Shear", ["tau_max", "sigma_new"])])
    good = exempted == [("M27", "tau_max")] and real == [
        ("M27", "Shear", ["sigma_new"])]
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  分离  已核实的与未核实的不互相遮蔽")

    exempted, real = split_exempted([("M22", "Bending", ["sigma_max"])])
    good = exempted == [("M22", "sigma_max")] and real == []
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  分离  全部核实过的模块不再报告为缺口")

    # [E-02] The same expiry check on the older EXEMPT table. A pair still
    # unreachable stays exempt; one that became reachable is stale.
    good = stale_exemptions([("M22", "Bending", [], ["sigma_max"])]) == []
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  仍然走不到的 EXEMPT 条目")
    good = stale_exemptions([("M22", "Bending", ["sigma_max"], [])]) == [
        ("M22", "sigma_max")]
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  已经过期的 EXEMPT 条目")

    # [E-02] --release scoping. A v1.1 module must be invisible at v1.0 and
    # visible at v1.1; a core module must be visible at both, because that is
    # how the gate behaved before the flag existed.
    scope_cases = [
        ({"tier": "extended", "release": "v1.1"}, "v1.0", False, "v1.1 模块在 v1.0 档外"),
        ({"tier": "extended", "release": "v1.1"}, "v1.1", True, "v1.1 模块在 v1.1 档内"),
        ({"tier": "core", "release": "v1.0"}, "v1.0", True, "core 模块在 v1.0 档内"),
        ({"tier": "core", "release": "v1.1"}, "v1.0", True, "core 压过 release 标签"),
        ({"tier": "extended", "release": "v2.0"}, "v1.1", False, "未来档不提前纳入"),
    ]
    for module, upto, want, label in scope_cases:
        good = in_release(module, upto) == want
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {'纳入' if want else '不纳入'}  {label}")

    # [E-02] A partial module is a real gap unless the canon says otherwise...
    held, real, stale = split_deferred(
        [("M03", "Curve", ["U_t"]), ("M99", "Other", ["x"])], [], {"M03": "需要数据导入"})
    good = ([m for m, _, _, _ in held] == ["M03"]
            and [m for m, _, _ in real] == ["M99"] and stale == [])
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  分离  正典推迟的与真缺口不互相遮蔽")

    # ...and a deferral whose module is now fully reachable is stale, not
    # silently honoured. This is the sample that proves the exemption itself
    # gets re-checked rather than trusted forever.
    _, _, stale = split_deferred([], ["M03"], {"M03": "需要数据导入"})
    good = stale == ["M03"]
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  已经过期的 ui_deferred")

    # A deferral for a module that is neither partial nor full (no entry at
    # all) must NOT be silently swallowed -- `none` fails before deferrals are
    # consulted, and this records that ordering.
    held, real, stale = split_deferred([], [], {"M03": "需要数据导入"})
    good = held == [] and real == [] and stale == []
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  一个入口都没有的模块不由 ui_deferred 处理")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--release", default="v1.0", choices=RELEASES,
                    help="检查到哪一档（含更早的档）；这一档里 partial 也失败")
    ap.add_argument("--write", action="store_true", help="刷新 posable 表")
    ap.add_argument("--app", type=Path, default=None,
                    help="Swift 界面层目录；不给就读 ci.toml 的 swift_app_dir")
    ap.add_argument("--kit", type=Path, default=None,
                    help="Swift 核心库目录；不给就读 ci.toml 的 swift_kit_dir")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_screen_reachability.py 自检")
        return self_test()

    root = args.root.resolve()
    # [M-03] 这三条路径原本写死成 MechanicsOne 的目录名。tools/ci 是三款共用
    # 的一份真身，所以在 StructureMechOne 上它找不到 `MechanicsOneApp/`，
    # **自己报「尚不适用」退 2**，被 runner 印成一行黄色的跳过——而这道闸门
    # 正是为抓「内核实现了但界面上到不了」而写的，那次审计在多解分支上找到
    # 了 16 处同类问题。风险最高的一道，被自己的默认路径关掉了。
    cfg = load_config(root)
    app_dir = args.app or cfg.path("swift_app_dir")
    kit_dir = args.kit or cfg.path("swift_kit_dir")
    spec_path = cfg.path("canon") or (root / "spec" / "specification.json")
    if not (root / "swift" / "Sources").is_dir() or not spec_path.is_file():
        print("尚不适用：Swift 侧或正典还不在 —— 阶段 05 之前正常", file=sys.stderr)
        return 2
    if app_dir is None or kit_dir is None or not app_dir.is_dir() \
            or not kit_dir.is_dir():
        print("✗ 摸不到 Swift 界面层或核心库目录：")
        print(f"    App  {app_dir}  {'有' if app_dir and app_dir.is_dir() else '不在'}")
        print(f"    Kit  {kit_dir}  {'有' if kit_dir and kit_dir.is_dir() else '不在'}")
        print("  swift/Sources 是在的——路径不对，不是「尚未开始」。")
        print("  在项目根的 ci.toml 里写 swift_app_dir / swift_kit_dir。")
        return 1

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    rows = classify(
        spec,
        reachable([p.read_text("utf-8") for p in app_dir.rglob("*.swift")],
                  [p.read_text("utf-8") for p in kit_dir.rglob("*.swift")]),
        args.release)
    deferred = {m["id"]: m["ui_deferred"] for m in spec["modules"]
                if m.get("ui_deferred")}

    if args.write:
        target = root / "docs" / "coverage-audit-posable.csv"
        write_table(target, rows)
        print(f"已写出 {target.relative_to(root)}（{len(rows)} 个模块）")

    none = [(i, t) for i, t, a, m in rows if not a]
    partial = [(i, t, m) for i, t, a, m in rows if a and m]
    full_ids = [i for i, t, a, m in rows if a and not m]

    # [A-12] Split each partial module's misses into verified-harmless and
    # everything else, so a new gap cannot hide among old, checked ones.
    exempted, real_partial = split_exempted(partial)
    # [E-02] Then set aside the ones the canon says are deliberately deferred,
    # and catch any deferral that has quietly gone stale.
    held, real_partial, stale = split_deferred(real_partial, full_ids, deferred)

    print(checked(len(rows), f"个 {args.release} 模块"))
    if not rows:
        print(f"✗ {args.release} 一个模块都没数到——这不是「全部可达」，"
              f"这是没检查。")
        return 1
    print(f"{args.release} 模块 {len(rows)} 个 · 全部输出可达 "
          f"{len(rows) - len(none) - len(partial)} · 部分 {len(real_partial)}"
          + (f"（另 {len(partial) - len(real_partial)} 个模块的缺口已核实为"
             f"假阳性，见下）" if len(partial) > len(real_partial) else "")
          + f" · 一个也到不了 {len(none)}")
    for mid, title, missing in real_partial:
        print(f"  − {mid} {title[:40]:<40} 声明了但走不到：{', '.join(missing)}")
    if exempted:
        print(f"\n（另 {len(exempted)} 处已核实的假阳性，走的是更通用的路径，"
              f"见 EXEMPT）：")
        for mid, sym in exempted:
            print(f"    {mid}.{sym}")
    if held:
        print(f"\n（另 {len(held)} 个模块的界面由正典明文推迟，"
              f"字段 ui_deferred）：")
        for mid, title, missing, why in held:
            print(f"    {mid} {title[:36]:<36} {', '.join(missing)}")
            print(f"        理由：{why}")
    if none:
        print(f"\n✗ {len(none)} 个 {args.release} 模块，界面上没有任何入口：")
        for mid, title in none:
            print(f"    {mid}  {title}")
        print("  内核实现了、conformance 比对过、对等测试点过名——"
              "而用户走不到。前面每一道闸门都会是绿的。")
        return 1
    rotten = stale_exemptions(rows)
    if rotten:
        print(f"\n✗ {len(rotten)} 条 EXEMPT 豁免已经过期：")
        for mid, sym in rotten:
            print(f"    {mid}.{sym}  这个符号现在真的到得了，"
                  f"请把 EXEMPT 里那一条删掉")
        print("  豁免说的是「界面走的是更通用的路径，这个闭式永远不会被调用」。"
              "有人加了一个读数真的调它，那句话就不再成立了。")
        return 1
    if stale:
        print(f"\n✗ {len(stale)} 条 ui_deferred 已经过期：")
        for mid in stale:
            print(f"    {mid}  这个模块的输出现在全部到得了，"
                  f"请把正典里那行 ui_deferred 删掉")
        print("  活儿干完了、借口没删。一条没人复核的豁免，"
              "就是这道闸门开始不算数的地方。")
        return 1
    if real_partial:
        print(f"\n✗ {len(real_partial)} 个 {args.release} 模块的界面只做了一半：")
        for mid, title, missing in real_partial:
            print(f"    {mid}  {title}  走不到：{', '.join(missing)}")
        print("  要么补上入口，要么在正典里为它写一行 ui_deferred 说明为什么。"
              "「以后再说」不写下来，就等于没有人记得。")
        return 1
    print(f"✓ 每个 {args.release} 模块的输出，界面上都到得了"
          + (f"（{len(held)} 个由正典明文推迟）" if held else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
