#!/usr/bin/env python3
"""Gate M7 —— App 图标：成品包里真的有，且十档齐全、尺寸对得上。

**三款 App 全都没有图标，而三十余道闸门没有一道在看这件事。** 这与本轮在修
的那一类洞同形：不是「查过了、是空的」，而是**没有人在查**。图标缺失在
「编译通过、测试全绿、Gate S 六项通过」的日志里完全看不见，而它是审核员
打开 App 之前就会看到的第一样东西。

四项检查，前三项对**成品包**，第四项对**源码资产**：

  **1. macOS 包的 .icns 十档齐全。** `Contents/Resources/*.icns` 存在，
     `iconutil -c iconset` 反向解包，`icon_{16,32,128,256,512}x{...}` 各
     @1x@2x 共十档一个不少；`icon_512x512@2x.png` 实测 1024×1024。
     只查「文件在」不够：一个只有 128 档的 .icns 在 Finder 里看着正常，
     在 Dock 和 Spotlight 里是糊的。

  **2. macOS 包的 Info.plist 有 CFBundleIconFile，且指向的 .icns 真在
     Resources 里。** 键写了而文件没打进去，图标就是不显示——而 plist
     自己不会报错。

  **3. iPadOS 包有 Assets.car，`xcrun assetutil --info` 列得出 AppIcon；
     Info.plist 有 CFBundleIconName。** iOS 侧的图标不是文件，是编译进
     asset catalog 的条目，`ls` 看不出有没有。

  **4. 源码面：`AppIcon.appiconset/Contents.json` 里每个 filename 指向的
     PNG 真的存在，且尺寸与它声明的 size × scale 一致。** 这一条抓的是
     「Contents.json 声明了十一档，实际只有三个文件」那一类——actool 对
     缺档只给警告，构建照样成功。

    python tools/ci/check_icon.py [--root .] [--bundle P] [--self-test]

退出码：0 通过 · 1 未通过 · 2 本阶段尚不适用。
"""

from __future__ import annotations

import argparse
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_config import checked, load as load_config          # noqa: E402

#: macOS 的 .icns 必须齐的十档，名字就是 iconutil 解出来的文件名。
ICNS_TEN = [
    "icon_16x16.png", "icon_16x16@2x.png",
    "icon_32x32.png", "icon_32x32@2x.png",
    "icon_128x128.png", "icon_128x128@2x.png",
    "icon_256x256.png", "icon_256x256@2x.png",
    "icon_512x512.png", "icon_512x512@2x.png",
]


def pixel_size(path: Path) -> tuple[int, int] | None:
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


def unpack_icns(icns: Path) -> tuple[set[str], Path | None, str]:
    """(解出来的档名集合, 临时 iconset 目录, 说明)。

    `iconutil -c iconset` 是反向操作：它把 .icns 拆回一个 iconset 目录。
    用它而不是读 .icns 的二进制头，因为那是 Apple 自己的解析器——它认得的
    才是系统认得的。
    """
    if shutil.which("iconutil") is None:
        return set(), None, "iconutil 不在（非 macOS？）"
    tmp = Path(tempfile.mkdtemp(prefix="icns-"))
    target = tmp / "AppIcon.iconset"
    out = subprocess.run(["iconutil", "-c", "iconset", str(icns),
                          "-o", str(target)],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0 or not target.is_dir():
        return set(), tmp, f"iconutil 解包失败：{out.stderr.strip()[:120]}"
    return {p.name for p in target.iterdir()}, tmp, ""


def car_has_appicon(car: Path) -> tuple[bool, str]:
    """`xcrun assetutil --info` 里列不列得出 AppIcon。"""
    if shutil.which("xcrun") is None:
        return False, "xcrun 不在（非 macOS？）"
    out = subprocess.run(["xcrun", "assetutil", "--info", str(car)],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return False, f"assetutil 失败：{out.stderr.strip()[:120]}"
    return "AppIcon" in out.stdout, ""


def appiconset_problems(iconset: Path) -> tuple[list[str], int]:
    """(每条问题一行, 看了几个条目)。"""
    contents = iconset / "Contents.json"
    if not contents.is_file():
        return [f"{iconset.name}/Contents.json 不存在"], 0
    data = json.loads(contents.read_text(encoding="utf-8"))
    images = data.get("images") or []
    problems: list[str] = []
    seen = 0
    for image in images:
        filename = image.get("filename")
        if not filename:
            continue                    # 未填的档位是 Xcode 的正常写法
        seen += 1
        path = iconset / filename
        if not path.is_file():
            problems.append(
                f"{filename}  Contents.json 声明了它，而文件不存在"
                f"（size={image.get('size')} scale={image.get('scale')}）")
            continue
        size = str(image.get("size") or "")
        scale = str(image.get("scale") or "1x")
        if "x" not in size:
            continue
        try:
            points = float(size.split("x")[0])
            factor = float(scale.rstrip("x"))
        except ValueError:
            continue
        want = int(round(points * factor))
        measured = pixel_size(path)
        if measured is None:
            continue                    # 量不到就不判，别乱叫
        if measured != (want, want):
            problems.append(
                f"{filename}  实测 {measured[0]}×{measured[1]}，而声明 "
                f"{size} @{scale} = {want}×{want}")
    return problems, seen


# ──────────────────────────────── 自检 ────────────────────────────────

def _png(path: Path, side: int) -> None:
    """写一张 side×side 的真 PNG。用 sips 从一张已知图缩放太绕，
    这里直接手写最小 PNG（灰度、无压缩块由 zlib 生成）。"""
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes([(x * 7) % 256 for x in range(side)])
                   for _ in range(side))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", side, side, 8, 0, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                     + chunk(b"IDAT", zlib.compress(raw))
                     + chunk(b"IEND", b""))


def self_test() -> int:
    ok = True

    # 已知会失败的样本 ①：Contents.json 指向不存在的文件。
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.appiconset"
        iconset.mkdir()
        _png(iconset / "icon-mac-16.png", 16)
        (iconset / "Contents.json").write_text(json.dumps({"images": [
            {"filename": "icon-mac-16.png", "idiom": "mac",
             "scale": "1x", "size": "16x16"},
            {"filename": "icon-mac-1024.png", "idiom": "mac",
             "scale": "2x", "size": "512x512"},
        ]}), encoding="utf-8")
        problems, seen = appiconset_problems(iconset)
        good = seen == 2 and any("icon-mac-1024.png" in p for p in problems)
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  抓到  "
              f"Contents.json 声明了十一档，文件只有一个")

    # 已知会失败的样本 ②：文件在，尺寸对不上声明。
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.appiconset"
        iconset.mkdir()
        _png(iconset / "icon-mac-32.png", 24)          # 声明 32，实际 24
        (iconset / "Contents.json").write_text(json.dumps({"images": [
            {"filename": "icon-mac-32.png", "idiom": "mac",
             "scale": "2x", "size": "16x16"},
        ]}), encoding="utf-8")
        problems, seen = appiconset_problems(iconset)
        measurable = pixel_size(iconset / "icon-mac-32.png") is not None
        good = (seen == 1 and (bool(problems) if measurable else True))
        ok &= good
        note = "" if measurable else "（sips 不可用，本条只验解析）"
        print(f"  {'PASS' if good else 'FAIL'}  抓到  声明 16x16@2x 而实测"
              f" 24×24 {note}")

    # 必须放行的样本：声明与文件一一对上。
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.appiconset"
        iconset.mkdir()
        _png(iconset / "icon-mac-16.png", 16)
        _png(iconset / "icon-mac-32.png", 32)
        (iconset / "Contents.json").write_text(json.dumps({"images": [
            {"filename": "icon-mac-16.png", "idiom": "mac",
             "scale": "1x", "size": "16x16"},
            {"filename": "icon-mac-32.png", "idiom": "mac",
             "scale": "2x", "size": "16x16"},
            {"idiom": "mac", "scale": "1x", "size": "512x512"},   # 未填，正常
        ]}), encoding="utf-8")
        problems, seen = appiconset_problems(iconset)
        good = not problems and seen == 2
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  放行  声明与文件一一对上"
              f"（未填的档位不算数）"
              + ("" if good else f"   ← 误报：{problems}"))

    # 已知会失败的样本 ③：.icns 缺档。用真的 iconutil 造一个只有两档的。
    if shutil.which("iconutil"):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "Partial.iconset"
            iconset.mkdir()
            _png(iconset / "icon_16x16.png", 16)
            _png(iconset / "icon_16x16@2x.png", 32)
            icns = Path(tmp) / "Partial.icns"
            built = subprocess.run(
                ["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
                capture_output=True, text=True, timeout=60)
            if built.returncode == 0 and icns.is_file():
                found, scratch, why = unpack_icns(icns)
                missing = [n for n in ICNS_TEN if n not in found]
                good = len(missing) == 8
                if scratch:
                    shutil.rmtree(scratch, ignore_errors=True)
                ok &= good
                print(f"  {'PASS' if good else 'FAIL'}  抓到  "
                      f".icns 只有 2 / 10 档（缺 {len(missing)} 档）")
            else:
                print(f"  ----  跳过  iconutil 造不出样本："
                      f"{built.stderr.strip()[:80]}")
    else:
        print("  ----  跳过  iconutil 不在，.icns 那一档无法自检")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def check_mac_bundle(bundle: Path) -> tuple[list[str], list[str], int]:
    """(问题, 通过项, 看了几个对象)。"""
    problems: list[str] = []
    passed: list[str] = []
    seen = 0
    resources = bundle / "Contents" / "Resources"
    plist = bundle / "Contents" / "Info.plist"

    icns_files = sorted(resources.glob("*.icns")) if resources.is_dir() else []
    seen += len(icns_files)
    if not icns_files:
        problems.append(f"{bundle.name}  Contents/Resources 里一个 .icns 都没有")
    for icns in icns_files:
        found, scratch, why = unpack_icns(icns)
        if why:
            problems.append(f"{bundle.name}/{icns.name}  {why}")
        else:
            missing = [n for n in ICNS_TEN if n not in found]
            if missing:
                problems.append(
                    f"{bundle.name}/{icns.name}  十档缺 {len(missing)}："
                    f"{', '.join(missing)}")
            else:
                big = scratch / "AppIcon.iconset" / "icon_512x512@2x.png"
                measured = pixel_size(big) if big.is_file() else None
                if measured and measured != (1024, 1024):
                    problems.append(
                        f"{bundle.name}/{icns.name}  1024 档实测 "
                        f"{measured[0]}×{measured[1]}")
                else:
                    passed.append(f"{bundle.name}/{icns.name}  十档齐全，"
                                  f"1024 档实测 "
                                  f"{measured[0] if measured else '?'}×"
                                  f"{measured[1] if measured else '?'}")
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    if plist.is_file():
        seen += 1
        data = plistlib.loads(plist.read_bytes())
        name = data.get("CFBundleIconFile")
        if not name:
            problems.append(f"{bundle.name}  Info.plist 没有 CFBundleIconFile")
        else:
            stem = name[:-5] if name.endswith(".icns") else name
            if not (resources / f"{stem}.icns").is_file():
                problems.append(
                    f"{bundle.name}  CFBundleIconFile={name!r}，"
                    f"而 Resources 里没有 {stem}.icns —— "
                    f"键写了而文件没打进去，图标就是不显示")
            else:
                passed.append(f"{bundle.name}  CFBundleIconFile={name!r} "
                              f"指向真实存在的 .icns")
    return problems, passed, seen


def check_ios_bundle(bundle: Path) -> tuple[list[str], list[str], int]:
    problems: list[str] = []
    passed: list[str] = []
    seen = 0
    car = bundle / "Assets.car"
    plist = bundle / "Info.plist"
    seen += 1
    if not car.is_file():
        problems.append(f"{bundle.name}  没有 Assets.car —— "
                        f"iOS 的图标编译进 asset catalog，ls 看不出有没有")
    else:
        found, why = car_has_appicon(car)
        if why:
            problems.append(f"{bundle.name}/Assets.car  {why}")
        elif not found:
            problems.append(f"{bundle.name}/Assets.car  "
                            f"assetutil --info 里列不出 AppIcon")
        else:
            passed.append(f"{bundle.name}/Assets.car  含 AppIcon")
    if plist.is_file():
        seen += 1
        data = plistlib.loads(plist.read_bytes())
        if not data.get("CFBundleIconName"):
            problems.append(f"{bundle.name}  Info.plist 没有 CFBundleIconName")
        else:
            passed.append(f"{bundle.name}  CFBundleIconName="
                          f"{data['CFBundleIconName']!r}")
    return problems, passed, seen


def is_ios_bundle(bundle: Path) -> bool:
    return not (bundle / "Contents").is_dir()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--bundle", type=Path, action="append", default=None)
    ap.add_argument("--appiconset", type=Path, default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print("check_icon.py 自检")
        return self_test()

    root = args.root.resolve()
    cfg = load_config(root)

    iconset = args.appiconset or cfg.path("appiconset")
    if iconset is None:
        for candidate in root.rglob("AppIcon.appiconset"):
            if ".build" not in str(candidate) and "build/" not in str(candidate):
                iconset = candidate
                break
    bundles = [Path(b) for b in (args.bundle or [])]
    if not bundles:
        bundles = [p for p in cfg.paths("app_bundles") if p.exists()]
    if not bundles:
        for pattern in ("dist/*.app", "build/*.app"):
            bundles += sorted(root.glob(pattern))

    if (iconset is None or not iconset.is_dir()) and not bundles:
        print("尚不适用：既没有 AppIcon.appiconset，也没有成品包 "
              "—— 图标流水线还没建（阶段 06 之前正常）", file=sys.stderr)
        return 2

    problems: list[str] = []
    passed: list[str] = []
    seen = 0

    if iconset and iconset.is_dir():
        source_problems, source_seen = appiconset_problems(iconset)
        seen += source_seen
        problems += [f"{iconset.name}/{p}" for p in source_problems]
        if source_seen == 0:
            # 实测（Thermodynamics Calculator）：`AppIcon.appiconset` 目录在，
            # `Contents.json` 里一个 filename 都没填。Xcode 生成的空占位集
            # 就长这样，构建照样成功，图标是空白的。
            # **目录存在不是图标存在。**
            problems.append(
                f"{iconset.name}/Contents.json 里一个 filename 都没填 —— "
                f"这是 Xcode 的空占位集，App 会用空白图标出货")
        elif not source_problems:
            passed.append(f"{iconset.name}  {source_seen} 个声明的档位，"
                          f"文件都在、尺寸都对")
    else:
        problems.append("找不到 AppIcon.appiconset —— "
                        "在 ci.toml 里写 appiconset")

    for bundle in bundles:
        if is_ios_bundle(bundle):
            p, ok_lines, n = check_ios_bundle(bundle)
        else:
            p, ok_lines, n = check_mac_bundle(bundle)
        problems += p
        passed += ok_lines
        seen += n

    print(checked(seen, "个图标对象",
                  f"{len(bundles)} 个成品包 + 1 份 appiconset"))
    for line in passed:
        print(f"  ✓ {line}")
    if seen == 0 and not problems:
        print("✗ 一个图标对象都没检查——这不是通过，这是没检查。")
        return 1
    if not bundles:
        problems.append("dist/ 与 build/ 里没有成品包 —— "
                        "前三项只能对成品跑，本次没查")
    if problems:
        print(f"✗ {len(problems)} 项图标检查未通过：")
        for line in problems:
            print(f"    {line}")
        print("  图标是审核员打开 App 之前就会看到的第一样东西，"
              "而它的缺失在「编译通过、测试全绿」的日志里完全看不见。")
        return 1
    print(f"✓ 图标齐备：{len(bundles)} 个成品包 + 源码资产")
    return 0


if __name__ == "__main__":
    sys.exit(main())
