"""Record immutable source provenance for the selected official rules snapshot."""

import hashlib
import json
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
extracts = json.loads((ROOT / "data/extracted/doc-extraction.json").read_text(encoding="utf-8"))
by_source = {Path(item["source"]).name: item for item in extracts}
sources = [
    {
        "document_id": "insurance_sales_behavior_order_2023_02",
        "title": "保险销售行为管理办法",
        "source_path": "法律法规/保险销售行为管理办法.doc",
        "document_status": "effective",
        "published_on": "2023-09-20",
        "effective_on": "2024-03-01",
        "official_source_url": "https://www.nfra.gov.cn/cn/view/pages/rulesDetail.html?docId=1129945",
        "extraction": by_source["保险销售行为管理办法.doc"],
    },
    {
        "document_id": "financial_network_marketing_order_2026_09",
        "title": "金融产品网络营销管理办法",
        "source_path": "法律法规/金融产品网络营销管理办法.pdf",
        "document_status": "effective",
        "published_on": "2026-04-21",
        "effective_on": "2026-09-30",
        "official_source_url": "https://www.samr.gov.cn/ggjgs/tzgg/art/2026/art_45df2e4c27674b2c82b9a5b4489b64ad.html",
        "extraction_method": "PyMuPDF page.get_text(sort=True)",
        "extraction_version": pymupdf.VersionBind,
        "verified": False,
    },
    {
        "document_id": "internet_insurance_supervision_order_2020_13",
        "title": "互联网保险业务监管办法",
        "source_path": "法律法规/互联网保险业务监管办法.doc",
        "document_status": "effective",
        "published_on": "2020-12-07",
        "effective_on": "2021-02-01",
        "official_source_url": "https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=949137",
        "extraction": by_source["互联网保险业务监管办法.doc"],
    },
]
for item in sources:
    source = ROOT / item["source_path"]
    item["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    if "extraction" in item:
        item["extraction"]["verified"] = False
    else:
        pdf = pymupdf.open(source)
        item["pdf_page_count"] = len(pdf)
        item["pdf_metadata"] = pdf.metadata
        item["extracted_page_char_counts"] = [len(page.get_text("text", sort=True)) for page in pdf]
        pdf.close()
result = {
    "ruleset_id": "official-v1-2026-10-11",
    "ruleset_mode": "official_snapshot",
    "snapshot_date": "2026-10-11",
    "source_inventory": str((ROOT / "reports/source-inventory.json").relative_to(ROOT)),
    "documents": sources,
    "corpus_published": False,
    "article_text_verified": False,
}
target = ROOT / "data/extracted/official-source-manifest.json"
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(target.relative_to(ROOT))
