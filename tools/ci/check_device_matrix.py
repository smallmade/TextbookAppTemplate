#!/usr/bin/env python3
"""Gate 06B / M4 —— 设备矩阵截图齐全性：设备 × 画面 × 深浅色，缺一格即未通过。

规范 v5.0 §7.1 与 M4。**每格每屏截图，深浅色各一。** 三款 App 的走查各抓到
6–7 个所有闸门都绿的真实缺陷，而它们只在屏幕上看得见：画面开在 `P_cr = 0`、
两画面同一符号反号、图画的是另一个模块的东西。

这道闸门不看图**画得对不对**——那是人的事。它看的是**有没有这一格**，以及
**这一格的尺寸对不对**。后者不是形式：一张按错窗口尺寸截的图，证明的是另一
台设备上的布局。

──────────────────────────────────────────────────────────────
文件名约定（三段，用 `__` 分隔，位置无关，大小写不敏感）：

    <walkthrough_dir>/<任意子目录>/<device>__<screen>__<appearance>.png

例：`docs/walkthrough/2026-09-02/ipad-pro-13-portrait__columns__dark.png`

任意子目录：日期目录、复走查目录都行。判据是**三段都出现在文件名里**，
不是路径深度——一道要求目录结构分毫不差的闸门，第一次复走查就会红。

设备清单与外观清单读 `ci.toml`（`devices` 表 + `appearances`）；画面清单从
`screens_source` 里的 `ScreenSpec(id:` 抽。三者任一缺失就退 2 并说明，而不是
拿一份猜出来的清单去判「齐全」。

尺寸用 `sips -g pixelWidth -g pixelHeight` 实测。@2x 的屏可以是点数的整数倍
（1×、2×、3×），别的比例判未通过——那通常意味着截图被缩放过，而缩放过的
截图证明不了布局。

    python tools/ci/check_device_matrix.py [--root .] [--self-test]

退出码：0 通过 · 1 未通过 · 2 矩阵尚未开始（说明理由）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

SCREEN_SPEC = re.compile(r'ScreenSpec\(\s*id:\s*"([^"]+)"')
#: 允许的像素倍率。1× 是 Mac 的非 Retina 外接屏，2× 是 Retina，3× 是
#: 部分 iPhone。别的倍率意味着图被缩放过。
SCALES = (1, 2, 3)


def screens(source: Path) -> list[str]:
    if not source.is_file():
        return []
    return SCREEN_SPEC.findall(source.read_text(encoding="utf-8",
                                                errors="ignore"))


def pixel_size(path: Path) -> tuple[int, int] | None:
    """(宽, 高)，实测。sips 不在时返回 None（不判红，说明查不了）。"""
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    width = height = None
    for line in out.stdout.splitlines():
        if "pixelWidth:" in line:
            width = int(line.split(":")[1])
        elif "pixelHeight:" in line:
            height = int(line.split(":")[1])
    return (width, height) if width and height else None


def cell_files(shots: list[Path], device: str, screen: str,
               appearance: str) -> list[Path]:
    """这一格的截图。三段都要出现在文件名里。"""
    want = (device.lower(), screen.lower(), appearance.lower())
    return [p for p in shots
            if all(part in p.stem.lower() for part in want)]


def size_ok(measured: tuple[int, int], device: dict) -> tuple[bool, str]:
    """实测像素与设备声明的点数，必须差一个整数倍率。"""
    want_w, want_h = int(device["width"]), int(device["height"])
    got_w, got_h = measured
    for scale in SCALES:
        if (got_w, got_h) == (want_w * scale, want_h * scale):
            return True, f"{got_w}×{got_h} = {want_w}×{want_h} @{scale}x"
    return False, (f"{got_w}×{got_h}，而 {device['name']} 声明 "
                   f"{want_w}×{want_h}（允许 @1x/@2x/@3x）")


# ──────────────────────────────── 自检 ────────────────────────────────

DEVICES = [{"name": "ipad-pro-13-portrait", "width": 1032, "height": 1376},
           {"name": "mac-default-window", "width": 1280, "height": 800}]


def self_test() -> int:
    ok = True
    shots = [Path("2026-09-02/ipad-pro-13-portrait__columns__light.png"),
             Path("2026-09-02/ipad-pro-13-portrait__columns__dark.png"),
             Path("2026-09-02/mac-default-window__columns__light.png")]

    found = cell_files(shots, "ipad-pro-13-portrait", "columns", "dark")
    good = len(found) == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  找到  三段齐全的那一格")

    missing = not cell_files(shots, "mac-default-window", "columns", "dark")
    ok &= missing
    print(f"  {'PASS' if missing else 'FAIL'}  抓到  缺 mac 的 dark 那一格")

    # 复走查放在别的子目录里，仍然要认。
    rerun = shots + [Path("2026-09-05/rerun/mac-default-window__columns__dark.png")]
    good = len(cell_files(rerun, "mac-default-window", "columns", "dark")) == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  复走查在别的子目录里")

    # 一个设备名是另一个的前缀时不许串格。
    tricky = [Path("a/ipad-pro-13-portrait-split__columns__light.png")]
    good = len(cell_files(tricky, "ipad-pro-13-portrait", "columns",
                          "light")) == 1
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  记录  子串匹配会把 -split 也算进"
          f"父设备（保守，宁可多算不漏格）")

    good, why = size_ok((2064, 2752), DEVICES[0])
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  @2x 尺寸：{why}")

    bad, why = size_ok((1600, 1000), DEVICES[1])
    ok &= not bad
    print(f"  {'PASS' if not bad else 'FAIL'}  抓到  被缩放过的截图：{why}")

    good, _ = size_ok((1280, 800), DEVICES[1])
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  @1x 的 Mac 窗口")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_device_matrix.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)
    devices = cfg.get("devices") or []
    appearances = cfg.get("appearances") or []
    shots_dir = cfg.path("walkthrough_dir")
    screens_source = cfg.path("screens_source")

    if not devices or not appearances:
        print("尚不适用：ci.toml 里没有 devices / appearances —— "
              "设备矩阵（规范 v5.0 §7.1）还没有清单。", file=sys.stderr)
        return 2
    if screens_source is None or not screens_source.is_file():
        print("尚不适用：找不到声明画面清单的源文件 —— "
              "界面层（阶段 06）之前正常。", file=sys.stderr)
        return 2
    names = screens(screens_source)
    if not names:
        print(f"✗ {screens_source.name} 里一个 ScreenSpec 都没解析到——"
              f"画面清单为空时无法核对矩阵。")
        return 1
    if shots_dir is None or not shots_dir.is_dir():
        print(f"尚不适用：设备矩阵尚未开始 —— {shots_dir} 还不存在。",
              file=sys.stderr)
        print(f"  要核对的是 {len(devices)} 设备 × {len(names)} 画面 × "
              f"{len(appearances)} 外观 = "
              f"{len(devices) * len(names) * len(appearances)} 格。",
              file=sys.stderr)
        return 2

    shots = sorted(p for p in shots_dir.rglob("*.png"))
    total = len(devices) * len(names) * len(appearances)
    missing: list[str] = []
    wrong_size: list[str] = []
    filled = 0
    unmeasured = 0

    for device in devices:
        for screen in names:
            for appearance in appearances:
                found = cell_files(shots, device["name"], screen, appearance)
                if not found:
                    missing.append(f"{device['name']} × {screen} × {appearance}")
                    continue
                filled += 1
                measured = pixel_size(found[0])
                if measured is None:
                    unmeasured += 1
                    continue
                good, why = size_ok(measured, device)
                if not good:
                    wrong_size.append(
                        f"{found[0].relative_to(shots_dir)}  {why}")

    print(checked(total, "格（设备 × 画面 × 外观）",
                  f"已填 {filled} · 缺 {len(missing)} · "
                  f"目录里共 {len(shots)} 张 png"))
    if total == 0:
        print("✗ 矩阵是空的——这不是通过，这是没检查。")
        return 1

    failed = False
    if missing:
        print(f"✗ 缺 {len(missing)} / {total} 格：")
        for line in missing[:25]:
            print(f"    {line}")
        if len(missing) > 25:
            print(f"    …… 另 {len(missing) - 25} 格")
        failed = True
    if wrong_size:
        print(f"✗ {len(wrong_size)} 张截图的尺寸不对：")
        for line in wrong_size[:15]:
            print(f"    {line}")
        print("  按错窗口尺寸截的图，证明的是另一台设备上的布局。")
        failed = True
    if unmeasured:
        print(f"⚠ {unmeasured} 张量不到尺寸（sips 不可用？），"
              f"这一部分本次没查。")

    if failed:
        return 1
    print(f"✓ {total} 格齐备，尺寸全部对得上")
    return 0


if __name__ == "__main__":
    sys.exit(main())
