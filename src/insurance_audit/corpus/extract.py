"""Read-only extractors used by the folder pipeline; no legal conclusions."""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

SUPPORTED = {".doc", ".docx", ".pdf", ".txt", ".md"}


def extract(path: Path, output: Path) -> tuple[list[str], dict]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError("Encrypted PDF requires an unlocked source")
            units = [page.get_text(sort=True) for page in document]
        tool, version = "PyMuPDF page.get_text(sort=True)", pymupdf.VersionBind
    elif suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            body = ET.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        units = [
            "".join(t.text or "" for t in p.findall(".//w:t", ns))
            for p in body.findall(".//w:p", ns)
        ]
        tool, version = "Python zipfile/XML DOCX body paragraphs", sys.version.split()[0]
    elif suffix in {".txt", ".md"}:
        units = path.read_text(encoding="utf-8-sig").splitlines()
        tool, version = "Python UTF-8 text", sys.version.split()[0]
    elif suffix == ".doc":
        target = output / "wps-result.json"
        subprocess.run(
            ["py", "-3.11", str(Path(__file__).with_name("wps_worker.py")), str(path), str(target)],
            check=True,
            timeout=90,
            capture_output=True,
        )
        result = json.loads(target.read_text(encoding="utf-8"))
        units, tool, version = result["units"], result["tool"], result["version"]
    else:
        raise ValueError(f"Unsupported source format: {suffix}")
    if not units or not any(text.strip() for text in units):
        raise ValueError("No readable text; scanned documents require a reviewed OCR extraction")
    return units, {"tool": tool, "tool_version": version}
