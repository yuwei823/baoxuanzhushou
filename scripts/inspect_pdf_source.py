"""Extract PDF pages for source review without publishing a ruleset."""

import hashlib
import json
from pathlib import Path

import pymupdf
from build_extraction_registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "法律法规" / "金融产品网络营销管理办法.pdf"
output = ROOT / "data" / "extracted"
output.mkdir(parents=True, exist_ok=True)
with pymupdf.open(source) as document:
    pages = [page.get_text("text", sort=True) for page in document]
    metadata = document.metadata
(output / "金融产品网络营销管理办法.metadata.json").write_text(
    json.dumps({
        "source": str(source.relative_to(ROOT)),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "extractor": "PyMuPDF page.get_text(sort=True)",
        "pymupdf_version": pymupdf.VersionBind,
        "pdf_page_count": len(pages),
        "metadata": metadata,
        "extracted_page_char_counts": [len(page) for page in pages],
        "verified": False,
    }, ensure_ascii=False, indent=2), encoding="utf-8"
)
(output / "金融产品网络营销管理办法.pages.json").write_text(
    json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8"
)
(output / "金融产品网络营销管理办法.txt").write_text(
    "\n\n".join(pages), encoding="utf-8"
)
with pymupdf.open(source) as document:
    preview = ROOT / "tmp" / "pdfs"
    preview.mkdir(parents=True, exist_ok=True)
    for index in {0, len(document) - 1}:
        document[index].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(
            preview / f"network-marketing-{index + 1}.png"
        )
print(json.dumps({"pages": len(pages), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                  "first_page": pages[0], "last_page": pages[-1]}, ensure_ascii=False))
build_registry()
