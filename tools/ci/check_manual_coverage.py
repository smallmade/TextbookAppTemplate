#!/usr/bin/env python3
"""Gate 07 / M6 —— 理论手册每个出货模块一节，使用手册每个画面一节。

规范 v5.0 §5.10 的固定结构：理论手册**每模块一节**（问题与适用范围 / 符号
与单位 / 公式与推导要点 / 数值方法与精度 / 多解与分支 / 护栏 / 验证 /
自拟例题）；使用手册**每画面一节**（用途、输入、输出、图、分支、典型任务）。

判据故意粗糙，和 `check_interface_review.py` 一样：只查**整节遗漏**，不查
文字质量。理由是它抓的那类缺陷就是整块的——手册生成器按一份手写的模块清单
跑，清单漏一个模块，那一节就整节不存在，而手册看起来完全正常。

判据（对 HTML 全文，标签剥掉后）：
  * 理论手册：每个出货模块的 **id** 或 **title** 至少出现一次；
  * 使用手册：每个画面的 **title** 至少出现一次。

两册哪一册是哪一册，由 `ci.toml` 的 `manual_paths` 的**顺序**定：第一项是
使用手册，第二项是理论手册（与规范里两册的排列顺序一致）。文件名里含
`theory` 的那一项优先认成理论手册，因为顺序会被人改而名字不会。

    python tools/ci/check_manual_coverage.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

TAG = re.compile(r"<[^>]+>")
SCREEN_SPEC = re.compile(r'ScreenSpec\(\s*id:\s*"([^"]+)",\s*title:\s*"([^"]+)"')


def plain(raw: str) -> str:
    """标签剥掉、实体还原。

    实体还原不是修饰：画面标题 `Riveted & Welded Joints` 在 HTML 里写作
    `Riveted &amp; Welded Joints`，不还原就有三个画面被报成「手册里没有这
    一节」——而三节都在。**一道会乱叫的闸门两天之内就会被关掉**，而这三条
    误报正是实测跑出来的。
    """
    return html.unescape(TAG.sub(" ", raw))


def text_of(path: Path) -> str:
    return plain(path.read_text(encoding="utf-8", errors="ignore"))


def shipping_modules(spec: dict) -> list[dict]:
    declared = (spec.get("meta") or {}).get("ships_in_v1")
    if declared:
        wanted = set(declared)
        return [m for m in spec["modules"] if m["id"] in wanted]
    return [m for m in spec["modules"]
            if str(m.get("release", "")).startswith("v1")
            or m.get("tier") == "core"]


def missing_modules(text: str, modules: list[dict]) -> list[str]:
    out = []
    for module in modules:
        mid, title = module["id"], module.get("title", "")
        if re.search(rf"\b{re.escape(mid)}\b", text):
            continue
        if title and title.lower() in text.lower():
            continue
        out.append(f"{mid} {title}"[:60])
    return out


def missing_screens(text: str, screens: list[tuple[str, str]]) -> list[str]:
    return [f"{sid} ({title})" for sid, title in screens
            if title.lower() not in text.lower()]


# ──────────────────────────────── 自检 ────────────────────────────────

SPEC = {"modules": [
    {"id": "M01", "release": "v1.0", "title": "Direct shear in a fastener"},
    {"id": "M02", "release": "v1.0", "title": "Bearing stress"},
]}
SCREENS = [("joints", "Riveted & Welded Joints"), ("columns", "Columns")]


def self_test() -> int:
    ok = True

    thin = "<h2>M01</h2><p>Direct shear ...</p>"
    caught = missing_modules(plain(thin), shipping_modules(SPEC))
    good = caught and caught[0].startswith("M02")
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  理论手册漏掉一个出货模块")

    full = "<h2>M01</h2><h2>M02</h2>"
    good = not missing_modules(plain(full), shipping_modules(SPEC))
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  每个模块都有一节")

    by_title = "<h2>Direct shear in a fastener</h2><h2>Bearing stress</h2>"
    good = not missing_modules(plain(by_title), shipping_modules(SPEC))
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  用标题而不是 id 分节也算")

    caught = missing_screens("Columns are covered here.", SCREENS)
    good = caught == ["joints (Riveted & Welded Joints)"]
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  使用手册漏掉一个画面")

    good = not missing_screens(
        "Riveted & Welded Joints ... Columns ...", SCREENS)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  每个画面都有一节")

    # 实测误报：标题里的 & 在 HTML 里是 &amp;。不还原实体，三个画面
    # 会被报成「手册里没有这一节」——而三节都在。
    entities = plain("<h2>Riveted &amp; Welded Joints</h2><h2>Columns</h2>")
    good = not missing_screens(entities, SCREENS)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  标题里的 &amp; 实体")

    # 已知会失败的样本：一份【空】手册。零节不是「全部覆盖」。
    caught = missing_modules("", shipping_modules(SPEC))
    good = len(caught) == 2
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  空手册（零节 ≠ 全覆盖）")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def pick_manuals(cfg) -> tuple[Path | None, Path | None]:
    """(使用手册, 理论手册)。名字里带 theory 的优先认成理论手册。"""
    paths = cfg.paths("manual_paths")
    if not paths:
        return None, None
    theory = next((p for p in paths if "theory" in str(p).lower()), None)
    manual = next((p for p in paths if p != theory), None)
    if theory is None and len(paths) >= 2:
        manual, theory = paths[0], paths[1]
    return manual, theory


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_manual_coverage.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    manual_path, theory_path = pick_manuals(cfg)
    if manual_path is None or theory_path is None:
        print("尚不适用：ci.toml 没有声明两册手册的位置（manual_paths）"
              "—— 阶段 07 之前正常", file=sys.stderr)
        return 2
    missing_files = [p for p in (manual_path, theory_path) if not p.is_file()]
    if missing_files:
        print(f"尚不适用：两册手册还没生成 —— "
              f"{[p.name for p in missing_files]}（阶段 07 之前正常）",
              file=sys.stderr)
        return 2

    spec_path = cfg.path("canon") or (root / "spec" / "specification.json")
    if not spec_path.is_file():
        print("尚不适用：还没有正典", file=sys.stderr)
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    modules = shipping_modules(spec)

    screens_source = cfg.path("screens_source")
    screens: list[tuple[str, str]] = []
    if screens_source and screens_source.is_file():
        screens = SCREEN_SPEC.findall(
            screens_source.read_text(encoding="utf-8", errors="ignore"))

    theory_text = text_of(theory_path)
    manual_text = text_of(manual_path)
    gone_modules = missing_modules(theory_text, modules)
    gone_screens = missing_screens(manual_text, screens)

    print(checked(len(modules) + len(screens), "个应有的小节",
                  f"理论 {len(modules)} 模块 · 使用 {len(screens)} 画面"))
    if not modules:
        print("✗ 出货模块一个都没数到——这不是「手册齐全」，这是没检查。")
        return 1

    failed = False
    if gone_modules:
        print(f"✗ 理论手册缺 {len(gone_modules)} / {len(modules)} 个模块的一节：")
        for line in gone_modules[:20]:
            print(f"    {line}")
        if len(gone_modules) > 20:
            print(f"    …… 另 {len(gone_modules) - 20} 个")
        failed = True
    else:
        print(f"✓ 理论手册：{len(modules)} 个出货模块各有一节")

    if not screens:
        print("⚠ 使用手册那一半没查：ci.toml 没有 screens_source，"
              "或里面一个 ScreenSpec 都没解析到。")
    elif gone_screens:
        print(f"✗ 使用手册缺 {len(gone_screens)} / {len(screens)} 个画面的一节：")
        for line in gone_screens:
            print(f"    {line}")
        failed = True
    else:
        print(f"✓ 使用手册：{len(screens)} 个画面各有一节")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
