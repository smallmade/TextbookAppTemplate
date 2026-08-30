#!/usr/bin/env python3
"""Render one page of a scanned second source to PNG, to be read by human eyes.

The public-domain second sources are 1969 and 1975 scans.  Their OCR text layer
is wrong often enough that a value taken from it is a coin flip -- and a wrong
layer-5 fixture is worse than no fixture at all, because layer 5 is the only
layer independent of the primary textbooks, so nothing else contradicts it.

So the division of labour is fixed:

    OCR finds the page.  Eyes read the number.

This tool deliberately does no OCR.  It turns a page into an image and stops.

    python tools/ci/render_source_page.py refs/AFFDL-....pdf 43 113 493

Page numbers are zero-based indices into the file, which is what
``pypdf`` reports and what the fixture's ``page_pdf`` column records; the
number printed on the page itself goes in ``page_printed``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import pypdf
except ImportError:                                          # pragma: no cover
    raise SystemExit("pypdf is needed to render source pages: pip install pypdf")


def render(pdf: Path, page: int, out_dir: Path) -> Path:
    """Write page ``page`` of ``pdf`` into ``out_dir`` as a PNG."""
    reader = pypdf.PdfReader(str(pdf))
    if not 0 <= page < len(reader.pages):
        raise SystemExit(f"{pdf.name} has {len(reader.pages)} pages; {page} asked for")

    images = reader.pages[page].images
    if not images:
        raise SystemExit(
            f"page {page} of {pdf.name} carries no embedded image. It is "
            "probably born-digital, in which case its text layer can be "
            "trusted and this tool is not the one you want.")

    out_dir.mkdir(parents=True, exist_ok=True)
    biggest = max(images, key=lambda image: len(image.data))
    raw = out_dir / f"{pdf.stem[:16]}_p{page}_raw{Path(biggest.name).suffix or '.tif'}"
    raw.write_bytes(biggest.data)

    png = out_dir / f"{pdf.stem[:16]}_p{page}.png"
    try:
        subprocess.run(["sips", "-s", "format", "png", str(raw), "--out", str(png)],
                       check=True, capture_output=True)
    finally:
        raw.unlink(missing_ok=True)
    return png


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    pdf = Path(argv[1])
    out_dir = Path(argv[2]) if not argv[2].isdigit() else Path("build/source-pages")
    pages = [int(a) for a in argv[2:] if a.isdigit()]
    for page in pages:
        print(render(pdf, page, out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
