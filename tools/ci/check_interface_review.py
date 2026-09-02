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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402


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
    ap.add_argument("--screens", type=Path, default=None,
                    help="声明画面清单的 Swift 文件；不给就读 ci.toml 的 screens_source")
    ap.add_argument("--review", type=Path, default=None,
                    help="走查记录 Markdown；默认 docs/interface-review.md")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_interface_review.py 自检")
        return self_test()

    root = args.root.resolve()
    # [M-03] 这条路径原本写死成 `MechanicsOneApp/RootView.swift`。在
    # StructureMechOne 上它报「尚不适用：RootView.swift 不存在」——而
    # `swift/Sources/StructureMechOneApp/RootView.swift` 确确实实存在，
    # 147 行。**理由本身是假的**，而 45 个画面的走查记录因此无人核对。
    cfg = load_config(root)
    root_view_path = args.screens or cfg.path("screens_source")
    if root_view_path is None:
        app_dir = cfg.path("swift_app_dir")
        root_view_path = (app_dir / "RootView.swift") if app_dir else None
    review_path = args.review or (root / "docs/interface-review.md")

    if root_view_path is None or not root_view_path.is_file():
        if not (root / "swift" / "Sources").is_dir():
            print("尚不适用：Swift 界面还没建（阶段 06 之前正常）",
                  file=sys.stderr)
            return 2
        print(f"✗ 摸不到声明画面清单的源文件：{root_view_path}")
        print("  swift/Sources 是在的——路径不对，不是「尚未开始」。")
        print("  在项目根的 ci.toml 里写 screens_source。")
        return 1
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
    print(checked(len(titles), "个画面", f"走查记录 {review_path.name}"))
    if missing:
        print(f"✗ {len(missing)} / {len(titles)} 个画面没有出现在走查记录里：")
        for line in missing:
            print(f"    {line}")
        return 1
    print(f"✓ 全部 {len(titles)} 个画面都出现在 docs/interface-review.md 里")
    return 0


if __name__ == "__main__":
    sys.exit(main())
