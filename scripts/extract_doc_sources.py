"""Read local legacy DOC sources using an isolated, hidden Microsoft Word instance.

Run with a Python that has pywin32. Never edits the source documents or publishes a corpus.
"""

import hashlib
import json
from pathlib import Path

import win32com.client

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "data" / "extracted"
    output.mkdir(parents=True, exist_ok=True)
    # WPS documents its external automation ProgID as kwps.application.
    word = win32com.client.DispatchEx("kwps.application")
    records = []
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        word.AutomationSecurity = 3  # Disable macros in opened documents.
        version = str(word.Version)
        for name in ["保险销售行为管理办法.doc", "互联网保险业务监管办法.doc"]:
            source = ROOT / "法律法规" / name
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            document = word.Documents.Open(
                str(source), ConfirmConversions=False, ReadOnly=True,
                AddToRecentFiles=False, Visible=False,
            )
            try:
                text = document.Content.Text
                paragraphs = [p.Range.Text for p in document.Paragraphs]
                target = output / (source.stem + ".txt")
                target.write_text(text.replace("\r", "\n"), encoding="utf-8")
                (output / (source.stem + ".paragraphs.json")).write_text(
                    json.dumps(paragraphs, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                records.append({
                    "source": str(source.relative_to(ROOT)), "sha256": before,
                    "extractor": "WPS COM Content.Text", "version": version,
                    "characters": len(text), "paragraphs": len(paragraphs),
                    "output": str(target.relative_to(ROOT)), "verified": False,
                })
            finally:
                document.Close(SaveChanges=0)
            if hashlib.sha256(source.read_bytes()).hexdigest() != before:
                raise RuntimeError("Source changed during read-only extraction")
    finally:
        word.Quit(SaveChanges=0)
    (output / "doc-extraction.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
