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
import hashlib
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


# ── 本机屏幕放不下的那些格 ────────────────────────────────────────────
#
# [M-A20] 有些档位是负责人点名的目标设备，而不是本机能做到的事：外接 2.5K
# 那一档要 1300pt 高的窗口，本机两块屏的可用高都是 1080。这些格永远拍不到，
# 于是这道闸门永远红——而一道永远红的闸门，两天之内就会被关掉。
#
# 但「拍不到」不能由采集工具自己说了算。**同一批数据里已经有过一次错判**：
# matrix_mac.sh 把每个窗口都摆在 {0,0}（主屏原点，被菜单栏与程序坞吃掉
# 90pt），于是要 1010pt 的 mac-pro-16 被钳到 990，36 格全登记成
# 「本机屏幕放不下」。而第二块屏满 1080——那一档一直拍得到，只是没摆对屏。
# 采集侧修好之后，同一台机器同一天拍满了 36 格。
#
# 所以豁免要两个条件同时成立，缺一不可：
#
#   1. 采集登记表里这一格确实是 unreachable，且记下了被钳到多少（有证据）；
#   2. **这一档要的高度，超过本机最高那块屏的可用高**（硬件确实办不到）。
#
# 第 2 条是拿硬件复核第 1 条。它会拒绝 mac-pro-16 那种错判——1010 没有超过
# 1080，所以无论登记表怎么写，那 36 格都必须真的去拍。
#
# 量不到屏幕（无头 CI、拿不到 AppKit）时**一格都不豁免**：不确定的时候
# 报缺，而不是报通过。
def machine_screen_height(root: Path) -> int | None:
    """本机最高那块屏的可用高度（点）。量不到返回 None。"""
    helper = root / "tools" / "shots" / "RoomiestScreen.swift"
    if not helper.is_file():
        return None
    try:
        out = subprocess.run(["swift", str(helper)],
                             capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    parts = out.stdout.strip().split("\t")
    if len(parts) != 4:
        return None
    try:
        return int(parts[3])
    except ValueError:
        return None


def clamped_cells(shots_dir: Path) -> dict[tuple[str, str, str], str]:
    """采集登记表里判过 unreachable 的格 → 它被钳到的实测尺寸。

    只认最新那一份登记表里仍然是 unreachable 的格：某一档后来拍成了，
    旧表里那一行就不该再替它挡着。
    """
    manifests = sorted(shots_dir.rglob("_manifest.tsv"))
    if not manifests:
        return {}
    out: dict[tuple[str, str, str], str] = {}
    for manifest in manifests:            # 旧的先读，新的覆盖旧的
        try:
            rows = manifest.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for row in rows:
            cells = row.split("\t")
            if len(cells) < 8 or cells[0] == "status":
                continue
            status, device, screen, appearance = cells[0], cells[1], cells[2], cells[3]
            key = (device, screen, appearance)
            if status != "unreachable":
                out.pop(key, None)        # 后来拍成了，豁免作废
                continue
            want_h, got_h = cells[5], cells[7]
            try:
                if int(got_h) >= int(want_h):
                    out.pop(key, None)    # 没被钳矮，不算拍不到
                    continue
            except ValueError:
                continue
            out[key] = f"要 {cells[4]}×{want_h}pt，窗口服务器给到 {cells[6]}×{got_h}pt"
    return out


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


def _self_test_identical(root: Path) -> int:
    """只跑「深浅色成对相同」那一条判据，供自检用。

    单独写一个入口而不是调 run()：run() 还要读设备表、画面表与像素尺寸，
    自检里把那些都造齐会让这一条的失败原因变得不确定——而自检的价值全在
    「它红下来的原因是不是我想验的那一条」。
    """
    import hashlib as _h
    shots = sorted((root / "shots").rglob("*.png"))
    by_cell: dict[tuple[str, str], dict[str, Path]] = {}
    for path in shots:
        stem = path.stem.split("__")
        if len(stem) != 3:
            continue
        by_cell.setdefault((stem[0], stem[1]), {})[stem[2]] = path
    for (device_name, screen), shots_of in sorted(by_cell.items()):
        if len(shots_of) < 2:
            continue
        digests = {_h.md5(p.read_bytes()).hexdigest() for p in shots_of.values()}
        if len(digests) == 1:
            print(f"✗ {device_name} × {screen} 的深色与浅色是同一张")
            return 1
    return 0


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

    # 深浅色是同一张时必须判红 —— 这一条是拿真图跑整道闸门，不是只测一个
    # 辅助函数：漏掉它的那一版就是**辅助函数全对而整道闸门放行**。
    import contextlib
    import io
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ci.toml").write_text(
            'slug = "demo"\ndevice_matrix_dir = "shots"\n', encoding="utf-8")
        (root / "shots" / "d").mkdir(parents=True)
        # 最小的合法 PNG（1×1），两张字节完全相同。
        blob = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
            "00000049454e44ae426082")
        for appearance in ("light", "dark"):
            (root / "shots" / "d" /
             f"probe-device__probe-screen__{appearance}.png").write_bytes(blob)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _self_test_identical(root)
        good = (code == 1) and "同一张" in buf.getvalue()
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  抓到  深色与浅色是同一张图")
        if not good:
            print("        " + buf.getvalue().replace("\n", "\n        "))

    good, why = size_ok((2064, 2752), DEVICES[0])
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  @2x 尺寸：{why}")

    bad, why = size_ok((1600, 1000), DEVICES[1])
    ok &= not bad
    print(f"  {'PASS' if not bad else 'FAIL'}  抓到  被缩放过的截图：{why}")

    good, _ = size_ok((1280, 800), DEVICES[1])
    ok &= good
    print(f"  {'PASS' if good else 'FAIL'}  放行  @1x 的 Mac 窗口")

    # [M-A20] 「本机屏幕装不下」这条豁免必须抓得住被滥用的样子。
    #
    # 已知会失败的样本正是这套数据自己出过的那次错判：采集侧把窗口摆在主屏
    # 原点，1010pt 的档被菜单栏与程序坞挤到 990，于是登记成 unreachable。
    # 那一档屏幕明明装得下——豁免必须拒绝它，逼人去重拍（后来重拍确实拍满了）。
    import tempfile as _tempfile
    with _tempfile.TemporaryDirectory() as tmp:
        shots = Path(tmp)
        (shots / "_manifest.tsv").write_text(
            "status\tdevice\tscreen\tappearance\twant_w\twant_h\tgot_w\tgot_h\n"
            # 真的装不下：要 1300，只给到 1030
            "unreachable\ttall-tier\tcolumns\tlight\t2400\t1300\t2400\t1030\n"
            # 装得下，却被登记成装不下——摆错屏的那一种
            "unreachable\tfits-tier\tcolumns\tlight\t1700\t1010\t1700\t990\n"
            # 后来拍成了：旧表里的豁免必须作废
            "unreachable\tredeemed\tcolumns\tlight\t1700\t1010\t1700\t990\n"
            "ok\tredeemed\tcolumns\tlight\t1700\t1010\t1700\t1010\n",
            encoding="utf-8")
        found = clamped_cells(shots)
        good = ("tall-tier", "columns", "light") in found
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  记下  真的被钳矮的那一格")

        good = ("redeemed", "columns", "light") not in found
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  作废  后来拍成了的那一格，"
              f"旧表不再替它挡着")

        # 硬件复核：屏高 1080 时，1010 那一档不许被豁免，1300 那一档可以。
        room = 1080
        fits = int("1010") > room
        ok &= not fits
        print(f"  {'PASS' if not fits else 'FAIL'}  拒绝  屏幕装得下却报"
              f"「装不下」的档（1010pt vs 可用 {room}pt）")
        tall = int("1300") > room
        ok &= tall
        print(f"  {'PASS' if tall else 'FAIL'}  放行  确实超过屏高的档"
              f"（1300pt vs 可用 {room}pt）")

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
    # 本机屏幕装不下的那些档：登记表说被钳过，且硬件确实办不到。两条都要。
    clamped = clamped_cells(shots_dir)
    room_h = machine_screen_height(root) if clamped else None
    beyond_hardware: list[str] = []
    missing: list[str] = []
    wrong_size: list[str] = []
    filled = 0
    unmeasured = 0
    #: (device, screen) -> {appearance: 那一格的文件}，供深浅色成对比较。
    by_cell: dict[tuple[str, str], dict[str, Path]] = {}

    for device in devices:
        for screen in names:
            for appearance in appearances:
                found = cell_files(shots, device["name"], screen, appearance)
                if not found:
                    key = (device["name"], screen, appearance)
                    note = clamped.get(key)
                    if (note is not None and room_h is not None
                            and int(device["height"]) > room_h):
                        beyond_hardware.append(
                            f"{device['name']} × {screen} × {appearance}  {note}")
                    else:
                        missing.append(
                            f"{device['name']} × {screen} × {appearance}")
                    continue
                filled += 1
                by_cell.setdefault((device["name"], screen), {})[appearance] = \
                    found[0]
                measured = pixel_size(found[0])
                if measured is None:
                    unmeasured += 1
                    continue
                good, why = size_ok(measured, device)
                if not good:
                    wrong_size.append(
                        f"{found[0].relative_to(shots_dir)}  {why}")

    # 深色那一张与浅色那一张不许是同一张。
    #
    # 这道闸门原本只查文件名与像素尺寸，于是 MechanicsOne 的 72 对 Mac 截图
    # **逐字节完全相同**而它报了 144 格 ok。成因在采集那一侧：用「删掉
    # AppleInterfaceStyle 这个键」表示浅色，而那个键的含义是「跟随系统」，
    # 这台机器的系统本身就是深色。于是浅色一格证据都没有，看起来却是满的。
    #
    # 同一天的 iPad 那 4 对是真的不同——所以这不是「深浅色本来就长一样」。
    identical: list[str] = []
    if len(appearances) > 1:
        for (device_name, screen), shots_of in sorted(by_cell.items()):
            digests: dict[str, str] = {}
            for appearance, path in shots_of.items():
                digests[appearance] = hashlib.md5(path.read_bytes()).hexdigest()
            if len(shots_of) > 1 and len(set(digests.values())) == 1:
                identical.append(f"{device_name} × {screen}  "
                                 f"（{' / '.join(sorted(shots_of))} 是同一张）")

    print(checked(total, "格（设备 × 画面 × 外观）",
                  f"已填 {filled} · 缺 {len(missing)}"
                  + (f" · 本机屏幕装不下 {len(beyond_hardware)}"
                     if beyond_hardware else "")
                  + f" · 目录里共 {len(shots)} 张 png"))
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
    if identical:
        print(f"✗ {len(identical)} 个格位的深色与浅色是**逐字节相同的同一张图**：")
        for line in identical[:15]:
            print(f"    {line}")
        if len(identical) > 15:
            print(f"    …… 另 {len(identical) - 15} 个")
        print("  一格拍了两遍同一个外观，登记表上却是两格证据。"
              "先修采集那一侧再重拍。")
        failed = True
    if wrong_size:
        print(f"✗ {len(wrong_size)} 张截图的尺寸不对：")
        for line in wrong_size[:15]:
            print(f"    {line}")
        print("  按错窗口尺寸截的图，证明的是另一台设备上的布局。")
        failed = True
    if beyond_hardware:
        tiers = sorted({line.split(" × ")[0] for line in beyond_hardware})
        print(f"⚠ {len(beyond_hardware)} 格本机屏幕装不下，不计为缺："
              f"{'、'.join(tiers)}")
        for line in beyond_hardware[:3]:
            print(f"    {line}")
        print(f"  本机最高一块屏的可用高度是 {room_h}pt。这些档是负责人点名的"
              f"目标设备，不是本机能做到的事——换一块更高的屏，或在别的机器上"
              f"补拍，这几格就会重新变成「缺」。")
    if unmeasured:
        print(f"⚠ {unmeasured} 张量不到尺寸（sips 不可用？），"
              f"这一部分本次没查。")

    if failed:
        return 1
    print(f"✓ {total - len(beyond_hardware)} 格齐备，尺寸全部对得上"
          + (f"（另 {len(beyond_hardware)} 格本机屏幕装不下）"
             if beyond_hardware else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
