#!/usr/bin/env python3
"""闸门 —— G-02：界面走查记录必须覆盖全部 ScreenSpec。

`docs/interface-review.md` 是 A-01/A-10 的验收证据。这道闸门检查的不是
走查写得好不好，是**写没写全**：`RootView.swift` 里 `Screens.all` 声明的
每一个画面 id，走查记录里都要提到它的标题。

判据故意粗糙（子串匹配标题，不解析 Markdown 表格），因为它要抓的是
「漏了一整个画面没写」这种整块遗漏，不是文字质量。

    python3 tools/ci/check_interface_review.py [--root .] [--self-test]

退出码：0 通过 · 1 有画面没被提到 · 2 尚不适用（还没有走查记录）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def screen_titles(root_view: str) -> dict[str, str]:
    """``{screen id: title}``，从 RootView.swift 里的 ScreenSpec 声明抽出。"""
    found: dict[str, str] = {}
    for match in re.finditer(
            r'ScreenSpec\(id:\s*"([^"]+)",\s*title:\s*"([^"]+)"', root_view):
        found[match.group(1)] = match.group(2)
    return found


def missing_titles(review: str, titles: dict[str, str]) -> list[str]:
    return [f"{screen_id} ({title})" for screen_id, title in titles.items()
            if title not in review]


def self_test() -> int:
    root_view = '''
        ScreenSpec(id: "a", title: "Alpha Screen",
                   subtitle: "x", symbol: "y", modules: [], built: true),
        ScreenSpec(id: "b", title: "Beta Screen",
                   subtitle: "x", symbol: "y", modules: [], built: true),
    '''
    titles = screen_titles(root_view)
    ok = True

    missing = missing_titles("Only Alpha Screen is mentioned here.", titles)
    caught = "b (Beta Screen)" in missing
    print(f"  {'PASS' if caught else 'FAIL'}  拒绝  漏掉一个画面")
    ok &= caught

    complete = missing_titles("Alpha Screen: fine. Beta Screen: also fine.",
                              titles)
    quiet = not complete
    print(f"  {'PASS' if quiet else 'FAIL'}  放行  两个画面都提到了")
    ok &= quiet

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_interface_review.py 自检")
        return self_test()

    root = args.root.resolve()
    root_view_path = root / "swift/Sources/MechanicsOneApp/RootView.swift"
    review_path = root / "docs/interface-review.md"

    if not root_view_path.is_file():
        print("尚不适用：RootView.swift 不存在", file=sys.stderr)
        return 2
    if not review_path.is_file():
        print("尚不适用：docs/interface-review.md 还没有——A-01 还没做",
              file=sys.stderr)
        return 2

    titles = screen_titles(root_view_path.read_text(encoding="utf-8"))
    if not titles:
        print("尚不适用：RootView.swift 里一个 ScreenSpec 都没解析到",
              file=sys.stderr)
        return 2

    review = review_path.read_text(encoding="utf-8")
    missing = missing_titles(review, titles)
    if missing:
        print(f"✗ {len(missing)} / {len(titles)} 个画面没有出现在走查记录里：")
        for line in missing:
            print(f"    {line}")
        return 1
    print(f"✓ 全部 {len(titles)} 个画面都出现在 docs/interface-review.md 里")
    return 0


if __name__ == "__main__":
    sys.exit(main())
