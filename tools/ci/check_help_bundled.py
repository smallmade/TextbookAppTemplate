#!/usr/bin/env python3
"""Gate 07 / M6 —— 两册手册必须在包里，而且 App 里有打开它们的代码路径。

规范 v5.0 §5.10：两册（使用手册、理论手册）交付到三处——**App 内 Help**、
站点、PDF。这道闸门只管第一处，因为只有它是「离线可用」这条护城河的落点，
也只有它会在打包时静默掉队：站点上有、源码里有链接、而 bundle 里没有。

两问，都要答「是」：

  **① 成品包的资源里有这两册。** 对 `.app` / `.ipa` / `.pkg` 查
  `Contents/Resources/`（macOS）或 bundle 根（iOS）。找的是目录或 HTML，
  名字由 `ci.toml` 的 `manual_paths` 的**目录名**推出（`site/manual/index.html`
  → 找 `manual`），这样项目改名字时闸门跟着改。

  **② App 源码里有打开它们的代码路径。** 光有文件不算数：Thermo 一度把
  手册放进了 Resources，而没有任何一个按钮打开它——文件在包里、用户到不了，
  与「不在包里」对用户是同一件事。判据是源码里同时出现资源查找
  （`Bundle.main.url` / `Bundle.module.url` / `NSWorkspace.open` /
  `WKWebView` / `openHelp`）与两册各自的名字。

包还没建的时候退 2 并说明；**源码这一半在没有包的时候仍然查**，因为它是
阶段 06 就该成立的事。

    python tools/ci/check_help_bundled.py [--root .] [--bundle PATH] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: 源码里「真的会去打开一个包内资源」的痕迹。
OPENS_RESOURCE = re.compile(
    r"Bundle\.main\.(url|path)|Bundle\.module\.(url|path)|"
    r"NSWorkspace\.shared\.open|WKWebView|WebView|"
    r"\bopenHelp\b|\bHelpBook\b|\bhelpURL\b|openWindow\s*\(")


def manual_names(cfg) -> list[str]:
    """两册在包里应该叫什么。取 `manual_paths` 每一项的目录名。

    `site/manual/index.html` → `manual`；`docs/theory.html` → `theory`。
    从配置推而不是写死 ("manual", "theory")，因为下一个项目会把它们叫别的
    名字，而一份写死的清单会安静地对着不存在的名字报「缺」。
    """
    names: list[str] = []
    for raw in (cfg.get("manual_paths") or []):
        path = Path(str(raw))
        names.append(path.parent.name if path.name.endswith(".html")
                     and path.parent.name not in ("", ".") else path.stem)
    return names


def bundle_resources(bundle: Path) -> Path | None:
    """macOS 是 Contents/Resources，iOS 是 bundle 根。"""
    if (bundle / "Contents" / "Resources").is_dir():
        return bundle / "Contents" / "Resources"
    if bundle.is_dir():
        return bundle
    return None


def in_bundle(resources: Path, name: str) -> bool:
    """这一册在不在？目录、`<name>.html`、`<name>/index.html` 都算。"""
    if (resources / name).is_dir():
        return any((resources / name).rglob("*.html"))
    return (resources / f"{name}.html").is_file()


def bundled_copies(resources: Path, name: str) -> list[Path]:
    """这一册在包里的那几个文件。"""
    if (resources / name).is_dir():
        return sorted((resources / name).rglob("*.html"))
    single = resources / f"{name}.html"
    return [single] if single.is_file() else []


def stale_against_source(resources: Path, site: Path, name: str) -> str | None:
    """包里那一份与站点那一份**内容**一样吗？不一样就返回一句话说明。

    此前这道闸门只问「在不在」。于是手册重写完、站点重建完，而 `dist/` 里
    那两个包还带着上一次打包时的旧文本——**闸门是绿的，而 App 里的手册是过期
    的**。实测差值：523 KB 对 557 KB。

    「在不在」和「是不是当前那一份」是两个问题，而只问前一个的检查，会在
    每一次「改了手册但没重新打包」时安静放行。这与本套件里另外两处同族：
    比较两份都过期的产物、以及深浅色截图其实是同一张。
    """
    packaged = bundled_copies(resources, name)
    if not packaged:
        return None                     # 不在包里，由 in_bundle 那一条去报
    source = site / name / "index.html"
    if not source.is_file():
        source = site / f"{name}.html"
    if not source.is_file():
        return None                     # 站点里没有源，无从比较
    want = source.read_bytes()
    for copy in packaged:
        if copy.read_bytes() == want:
            return None
    sizes = " / ".join(f"{c.stat().st_size:,}" for c in packaged)
    return (f"{name}：包里那一份与 site/ 的不是同一份内容"
            f"（包 {sizes} 字节，站点 {len(want):,} 字节）"
            f"——手册重建过而这个包没有重新打，App 里的是旧的")


def source_opens(sources: str, names: list[str]) -> list[str]:
    """哪几册在源码里找不到打开它的代码路径。"""
    if not OPENS_RESOURCE.search(sources):
        return list(names)          # 一处资源查找都没有：全都到不了
    return [n for n in names if not re.search(rf"\b{re.escape(n)}\b",
                                              sources, re.I)]


# ──────────────────────────────── 自检 ────────────────────────────────

def self_test() -> int:
    import tempfile
    ok = True
    names = ["manual", "theory"]

    with tempfile.TemporaryDirectory() as tmp:
        res = Path(tmp) / "A.app" / "Contents" / "Resources"
        (res / "manual").mkdir(parents=True)
        (res / "manual" / "index.html").write_text("x", encoding="utf-8")
        # theory 故意不放进去 —— 已知会失败的样本一：只装了一册。
        missing = [n for n in names if not in_bundle(res, n)]
        good = missing == ["theory"]
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  抓到  包里只装了一册")

        (res / "theory.html").write_text("x", encoding="utf-8")
        missing = [n for n in names if not in_bundle(res, n)]
        good = not missing
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  放行  两册都在"
              f"（一个是目录，一个是单文件）")

    # 已知会失败的样本二：文件在包里，而没有任何代码打开它。
    silent = 'struct V: View { var body: some View { Text("Hello") } }'
    good = source_opens(silent, names) == names
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  包里有文件，"
          f"源码里一处资源查找都没有")

    half = 'let u = Bundle.main.url(forResource: "manual", withExtension: nil)'
    good = source_opens(half, names) == ["theory"]
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  抓到  只打开了一册")

    both = ('enum HelpBook { case manual, theory }\n'
            'let u = Bundle.main.url(forResource: name, withExtension: nil)')
    good = not source_opens(both, names)
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  两册都有打开的代码路径")

    good = manual_names(_FakeConfig({"manual_paths":
                                     ["site/manual/index.html",
                                      "site/theory/index.html"]})) == names
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  推名  从 manual_paths 推出册名，"
          f"而不是写死")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


class _FakeConfig:
    def __init__(self, data):
        self.data = data

    def get(self, key, default=None):
        return self.data.get(key, default)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--bundle", type=Path, action="append", default=None,
                    help="成品包；不给就读 ci.toml 的 app_bundles，再看 dist/ 与 build/")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_help_bundled.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    names = manual_names(cfg)
    if not names:
        print("尚不适用：ci.toml 没有声明 manual_paths —— 两册手册"
              "（阶段 07）还没有位置", file=sys.stderr)
        return 2

    # —— 源码那一半，随时可查 ——
    app_dir = cfg.path("swift_app_dir")
    if app_dir is None or not app_dir.is_dir():
        print("尚不适用：界面层还没建（阶段 06 之前正常）", file=sys.stderr)
        return 2
    sources = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                        for p in app_dir.rglob("*.swift"))
    unreachable = source_opens(sources, names)

    # —— 成品那一半 ——
    bundles = [Path(b) for b in (args.bundle or [])]
    if not bundles:
        bundles = [p for p in cfg.paths("app_bundles") if p.exists()]
    if not bundles:
        for pattern in ("dist/*.app", "build/*.app", "dist/*.ipa"):
            bundles += sorted(root.glob(pattern))

    print(checked(len(names) * max(len(bundles), 1), "个「册 × 包」组合",
                  f"{len(names)} 册 × {len(bundles)} 个包"))

    failed = False
    if unreachable:
        print(f"✗ {len(unreachable)} 册在 App 源码里没有打开它的代码路径："
              f"{unreachable}")
        print("  文件在包里而用户到不了，与不在包里对用户是同一件事。")
        failed = True
    else:
        print(f"✓ {len(names)} 册各有打开它的代码路径")

    if not bundles:
        print("⏸ 成品那一半没查：dist/ 与 build/ 里还没有包。")
        print("  源码这一半已经查过了；打完包要再跑一次。")
        return 1 if failed else 0

    for bundle in bundles:
        resources = bundle_resources(bundle)
        if resources is None:
            print(f"✗ {bundle.name} 不是一个能查的包")
            failed = True
            continue
        missing = [n for n in names if not in_bundle(resources, n)]
        if missing:
            print(f"✗ {bundle.name} 的资源里缺 {missing}")
            print(f"    查的是 {resources}")
            failed = True
        else:
            site = root / "site"
            stale = [s for s in (stale_against_source(resources, site, n)
                                 for n in names) if s]
            if stale:
                print(f"✗ {bundle.name} 的资源里两册都在，但不是当前那一份：")
                for line in stale:
                    print(f"    {line}")
                failed = True
            else:
                print(f"✓ {bundle.name} 的资源里两册齐备，且与 site/ 逐字节相同")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
