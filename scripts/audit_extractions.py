"""Structural quality checks for extracts; passing does not mean legal review is complete."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "extracted"
DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNITS = {"十": 10, "百": 100, "千": 1000}
MARKER = re.compile(r"^\s*第([〇零一二三四五六七八九十百千]+)条")


def chinese_number(value: str) -> int:
    total = current = 0
    for char in value:
        if char in DIGITS:
            current = DIGITS[char]
        else:
            unit = UNITS[char]
            total += (current or 1) * unit
            current = 0
    return total + current


def sequence_report(path: Path, expected_end: int) -> dict:
    paragraphs = json.loads(path.read_text(encoding="utf-8"))
    rows = [(i, chinese_number(m.group(1)), len(p.strip()))
            for i, p in enumerate(paragraphs)
            if (m := MARKER.match(p))]
    numbers = [row[1] for row in rows]
    expected = list(range(1, expected_end + 1))
    return {
        "source_extract": path.name,
        "paragraph_count": len(paragraphs),
        "article_heading_count": len(rows),
        "ordered_unique_contiguous": numbers == expected,
        "missing_ids": sorted(set(expected) - set(numbers)),
        "duplicate_ids": sorted(n for n in set(numbers) if numbers.count(n) > 1),
        "short_heading_paragraphs": [n for _, n, chars in rows if chars < 35],
        "first_article_chars": rows[0][2] if rows else 0,
        "last_article_chars": rows[-1][2] if rows else 0,
        "verified": False,
    }


def main() -> None:
    docs = [
        ("保险销售行为管理办法.paragraphs.json", 50),
        ("互联网保险业务监管办法.paragraphs.json", 83),
    ]
    reports = [sequence_report(OUT / name, end) for name, end in docs]
    pages = json.loads((OUT / "金融产品网络营销管理办法.pages.json").read_text(encoding="utf-8"))
    pdf_text = "\n".join(pages)
    pdf_numbers = [chinese_number(m.group(1)) for line in pdf_text.splitlines()
                   if (m := MARKER.match(line))]
    pdf_expected = list(range(1, 40))
    pdf_path = ROOT / "法律法规" / "金融产品网络营销管理办法.pdf"
    reports.append({
        "source": str(pdf_path.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "page_count": len(pages),
        "article_heading_count": len(pdf_numbers),
        "ordered_unique_contiguous": pdf_numbers == pdf_expected,
        "missing_ids": sorted(set(pdf_expected) - set(pdf_numbers)),
        "duplicate_ids": sorted(n for n in set(pdf_numbers) if pdf_numbers.count(n) > 1),
        "nonempty_pages": sum(bool(page.strip()) for page in pages),
        "verified": False,
    })
    result = {
        "ruleset_id": "official-v1-2026-10-11",
        "tool": "Python structural marker check; WPS COM / PyMuPDF extracts",
        "records": reports,
        "structural_checks_passed": all(
            r["ordered_unique_contiguous"] for r in reports
        ),
        "legal_text_verified": False,
        "human_review_required": True,
    }
    target = OUT / "source-audit.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
