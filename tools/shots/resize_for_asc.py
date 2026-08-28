#!/usr/bin/env python3
"""按 ASC 实测尺寸转换截图。

    python resize_for_asc.py <母版目录> <输出目录> [--family iphone|ipad|mac]

ASC 的 iPhone 上传框实测只收 6.5 英寸规格；6.9 英寸的 1320x2868 被当场
拒收。母版照常用最新模拟器抓，交付前等比缩放 + 居中裁到 1284x2778。

用 macOS 自带的 sips，不引第三方库——核心零依赖的纪律，工具链也守。
"""

import argparse
import subprocess
import sys
from pathlib import Path

TARGET = {"iphone": (1284, 2778), "ipad": (2064, 2752), "mac": (2880, 1800)}


def convert(src: Path, dst: Path, w: int, h: int) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # 先等比缩放到「至少覆盖」目标尺寸，再居中裁到精确尺寸。
    # 顺序不能反：先裁后缩会丢掉边缘内容。
    r = subprocess.run(
        ["sips", "--resampleHeightWidthMax", str(max(w, h)),
         str(src), "--out", str(dst)],
        capture_output=True)
    if r.returncode != 0:
        print(f"  ✗ {src.name}: sips 缩放失败", file=sys.stderr)
        return False
    r = subprocess.run(["sips", "--cropToHeightWidth", str(h), str(w), str(dst)],
                       capture_output=True)
    if r.returncode != 0:
        print(f"  ✗ {src.name}: sips 裁切失败", file=sys.stderr)
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--family", choices=sorted(TARGET), default="iphone")
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"找不到母版目录：{args.src}", file=sys.stderr)
        return 2
    w, h = TARGET[args.family]
    print(f"目标尺寸（ASC 实测接受值）：{w}x{h}\n")

    ok = 0
    for png in sorted(args.src.glob("*.png")):
        if convert(png, args.dst / png.name, w, h):
            print(f"  ✓ {png.name} → {w}x{h}")
            ok += 1
    print(f"\n{ok} 张已转换 → {args.dst}")
    print("下一步：python tools/ci/check_screenshots.py <输出目录的上层>")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
