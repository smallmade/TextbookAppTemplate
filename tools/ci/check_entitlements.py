#!/usr/bin/env python3
"""Gate —— entitlements 里声明的能力，代码里真的在用吗。

    python tools/ci/check_entitlements.py swift/App/<Name>.entitlements swift/Sources/<Name>App

一把 entitlement 是一句对沙盒说的话：「允许我做这件事」。如果代码里根本没有
会用到那件事的 API，这句话就是一个没有代码背书的能力声明——跟正典声明了内核
给不出的东西、豁免表没人复核，是同一类缺陷，只是这次长在 entitlements 里。

MechanicsOne 的 `files.user-selected.read-write` 就是这样被发现的：隐私页说
「entitlements 只有两把」，其中一把写着「为导出功能预留」，而导出早被 A-11
推迟到 v2、A-10 确认菜单栏没有 Export 命令——那把键从那一刻起就没有代码在用。

判据保守：一个能力被登记为"需要某个 API"，代码里一个都没出现，才算缺口；
`ANY_OF` 允许同一个能力有多种实现方式（比如两种不同的存盘面板 API）。
表外的 entitlement key 一律跳过，不是这道闸门要管的范围——它管的是"声明了
你知道要检查什么，就把它加进 ANY_OF"，不是穷举 Apple 的每一把钥匙。
"""

from __future__ import annotations

import plistlib
import re
import sys
from pathlib import Path

#: entitlement key -> 至少一个要出现在源码里的 API 名（写全名而非正则片段，
#: 避免 "URL" 这种词到处误中）。只收本项目系列实际用过或用得上的几把；
#: 新用到一把没在表里的 entitlement 时，先把它加进来，而不是让闸门放行。
ANY_OF: dict[str, tuple[str, ...]] = {
    "com.apple.security.files.user-selected.read-write": (
        "fileImporter", "fileExporter", "NSOpenPanel", "NSSavePanel"),
    "com.apple.security.files.user-selected.read-only": (
        "fileImporter", "NSOpenPanel"),
    "com.apple.security.network.client": (
        "URLSession", "NWConnection", "URLRequest"),
    "com.apple.security.network.server": (
        "NWListener",),
    "com.apple.security.device.camera": (
        "AVCaptureSession", "AVCaptureDevice"),
    "com.apple.security.device.microphone": (
        "AVCaptureSession", "AVAudioEngine"),
    "com.apple.security.personal-information.location": (
        "CLLocationManager",),
}


def source_text(root: Path) -> str:
    chunks = []
    for path in root.rglob("*.swift"):
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def unbacked_entitlements(plist_path: Path, source: str) -> list[str]:
    data = plistlib.loads(plist_path.read_bytes())
    unbacked = []
    for key, value in data.items():
        if value is not True or key not in ANY_OF:
            continue
        if not any(api in source for api in ANY_OF[key]):
            unbacked.append(key)
    return unbacked


def self_test() -> int:
    print("check_entitlements.py 自检")
    ok = True

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with_file_key = Path(tmp) / "with-file-key.entitlements"
        with_file_key.write_bytes(plistlib.dumps({
            "com.apple.security.app-sandbox": True,
            "com.apple.security.files.user-selected.read-write": True,
        }))
        sandbox_only = Path(tmp) / "sandbox-only.entitlements"
        sandbox_only.write_bytes(plistlib.dumps({
            "com.apple.security.app-sandbox": True,
        }))

        good = unbacked_entitlements(with_file_key, "struct Foo {}") == [
            "com.apple.security.files.user-selected.read-write"]
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  抓到  声明了但代码里没有对应 API"
              "（这正是 A-20 那把键当时的样子）")

        good = unbacked_entitlements(
            with_file_key, "Text().fileExporter(isPresented: $x) { }") == []
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  放行  声明了且代码里用到了")

        good = unbacked_entitlements(sandbox_only, "struct Foo {}") == []
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  放行  表外的 key（沙盒本身）不被检查")

    print("\n自检通过——闸门确实在工作" if ok else "\n自检失败")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    plist_path, src_root = Path(sys.argv[1]), Path(sys.argv[2])
    if not plist_path.is_file():
        print(f"找不到 entitlements：{plist_path}", file=sys.stderr)
        return 2
    if not src_root.is_dir():
        print(f"找不到源码目录：{src_root}", file=sys.stderr)
        return 2

    unbacked = unbacked_entitlements(plist_path, source_text(src_root))
    if unbacked:
        print(f"✗ {len(unbacked)} 把 entitlement 声明了能力，代码里没有对应 API：")
        for key in unbacked:
            print(f"    {key}  （需要以下之一：{', '.join(ANY_OF[key])}）")
        print("  一把没有代码背书的 entitlement，是能力声明，不是能力。"
              "功能真做出来时把它加回来，不要走在功能前面。")
        return 1
    print("✓ entitlements 里声明的每一项能力，代码里都有对应的 API 在用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
