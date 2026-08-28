#!/usr/bin/env python3
"""Gate 07 —— 截图尺寸校验（ASC 实测值，不是文档值）。

    python check_screenshots.py submission/screenshots/

ASC 的 iPhone 上传框实测只收 6.5 英寸规格；6.9 英寸的 1320x2868 被当场
拒收（Passthrough 实测）。母版照常用最新模拟器抓，交付前等比缩放居中裁。

不依赖任何第三方库——直接读 PNG 头。核心零依赖的纪律，工具链也守。
"""

import struct
import sys
from pathlib import Path

ACCEPTED = {
    "iphone": {(1284, 2778), (2778, 1284), (1242, 2688), (2688, 1242)},
    "ipad":   {(2064, 2752), (2752, 2064), (2048, 2732), (2732, 2048)},
    "mac":    {(1280, 800), (1440, 900), (2560, 1600), (2880, 1800)},
}
REJECTED_KNOWN = {(1320, 2868): "6.9 英寸规格，ASC 上传框实测当场拒收"}


def png_size(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as fh:
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        fh.read(4)
        if fh.read(4) != b"IHDR":
            return None
        return struct.unpack(">II", fh.read(8))


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python check_screenshots.py <screenshots 目录>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    if not root.is_dir():
        print(f"找不到目录：{root}", file=sys.stderr)
        return 2

    errors, count = [], 0
    for png in sorted(root.rglob("*.png")):
        size = png_size(png)
        if size is None:
            errors.append(f"{png.name}: 不是合法 PNG")
            continue
        count += 1
        rel = png.relative_to(root)
        family = next((k for k in ACCEPTED if k in str(rel).lower()), None)
        if family is None:
            print(f"  − {rel}  {size[0]}x{size[1]}  （目录名未标明设备族，跳过）")
            continue
        if size in ACCEPTED[family]:
            print(f"  ✓ {rel}  {size[0]}x{size[1]}")
        else:
            why = REJECTED_KNOWN.get(size, "不在 ASC 实测接受的尺寸内")
            errors.append(f"{rel}: {size[0]}x{size[1]} —— {why}")

    if not count:
        print("  − 没有找到 PNG")
    if errors:
        print()
        for e in errors:
            print(f"  ✗ {e}")
        print(f"\n  接受的尺寸：iPhone 1284x2778 · iPad 13\" 2064x2752")
        return 1
    print(f"\n✓ 截图尺寸通过：{count} 张")
    return 0


if __name__ == "__main__":
    sys.exit(main())
