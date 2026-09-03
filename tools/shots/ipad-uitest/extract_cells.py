#!/usr/bin/env python3
"""[M-A21] Turn a UI-test result bundle into device-matrix cells.

    python3 extract_cells.py <result.xcresult> <out-dir> <device> <appearance>

The test attaches one screenshot per screen, named by the screen's id. Xcode
appends its own suffix (`stress-point_1_<uuid>.png`), so the id is recovered
from the prefix before the first underscore-digit group rather than by trusting
the whole name.

Every attachment is renamed into the matrix's own three-part convention so the
gate can find it: `<device>__<screen>__<appearance>.png`.

Exits 1 if it wrote nothing. A run that extracts zero files while reporting
success is the failure this whole work package exists to remove -- the previous
iPad capture reported "ok" on cells whose files were left over from a run days
earlier.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

SUFFIX = re.compile(r"_\d+_[0-9A-Fa-f-]{36}\.png$")


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    bundle, out_dir, device, appearance = (Path(sys.argv[1]), Path(sys.argv[2]),
                                           sys.argv[3], sys.argv[4])
    manifest = bundle / "manifest.json"
    if not manifest.is_file():
        print(f"✗ no manifest.json in {bundle} —— attachments were not exported",
              file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for test in json.loads(manifest.read_text(encoding="utf-8")):
        for att in test.get("attachments", []):
            name = att.get("suggestedHumanReadableName") or ""
            exported = att.get("exportedFileName") or ""
            if not name.endswith(".png") and not SUFFIX.search(name):
                continue
            screen = SUFFIX.sub("", name)
            if not screen or screen == name:
                continue
            src = bundle / exported
            if not src.is_file():
                print(f"  ⚠ manifest names {exported}, which is not there")
                continue
            dst = out_dir / f"{device}__{screen}__{appearance}.png"
            shutil.copy2(src, dst)
            written += 1
    print(f"   取出 {written} 格 → {out_dir}")
    if written == 0:
        print("✗ 一格都没取出来——零格不是成功", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
