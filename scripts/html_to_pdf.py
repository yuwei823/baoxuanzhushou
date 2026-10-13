"""Render the presentation HTML to a 16:9 PDF with Chrome or Edge.

By default this converts ``src/insurance_audit/static/intro.html`` to
``output/pdf/insurance-marketing-audit-introduction.pdf``.
"""

from __future__ import annotations

import argparse
import http.server
import os
import shutil
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from functools import partial
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "src" / "insurance_audit" / "static" / "intro.html"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "pdf" / "insurance-marketing-audit-introduction.pdf"


def browser_candidates() -> list[Path]:
    """Return common Chrome and Edge locations in preference order."""
    paths: list[Path] = []
    for variable, suffix in (
        ("PROGRAMFILES", "Google/Chrome/Application/chrome.exe"),
        ("PROGRAMFILES", "Microsoft/Edge/Application/msedge.exe"),
        ("PROGRAMFILES(X86)", "Microsoft/Edge/Application/msedge.exe"),
        ("LOCALAPPDATA", "Google/Chrome/Application/chrome.exe"),
    ):
        base = os.environ.get(variable)
        if base:
            paths.append(Path(base) / Path(suffix))
    for command in ("chrome", "msedge", "chromium", "chromium-browser"):
        located = shutil.which(command)
        if located:
            paths.append(Path(located))
    return paths


def find_browser(explicit: Path | None) -> Path:
    if explicit:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Browser executable not found: {path}")
        return path
    for path in browser_candidates():
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(
        "Chrome or Edge was not found. Pass its executable with --browser."
    )


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serve local assets without writing browser requests to the console."""

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def serve_directory(directory: Path):
    """Serve the HTML directory locally so relative assets load reliably."""
    handler = partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def validate_pdf(path: Path) -> int | None:
    if not path.is_file() or path.stat().st_size < 1_000:
        raise RuntimeError(f"PDF was not created correctly: {path}")
    if path.read_bytes()[:5] != b"%PDF-":
        raise RuntimeError(f"Output is not a PDF: {path}")
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    pages = len(PdfReader(path).pages)
    if pages < 1:
        raise RuntimeError("The generated PDF contains no pages")
    return pages


def render(input_html: Path, output_pdf: Path, browser: Path) -> int | None:
    input_html = input_html.expanduser().resolve()
    output_pdf = output_pdf.expanduser().resolve()
    if not input_html.is_file():
        raise FileNotFoundError(f"Input HTML not found: {input_html}")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    with (
        tempfile.TemporaryDirectory(prefix="insurance-audit-pdf-") as profile,
        serve_directory(input_html.parent) as base_url,
    ):
        url = f"{base_url}/{input_html.name}"
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--run-all-compositor-stages-before-draw",
            "--print-to-pdf-no-header",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={output_pdf}",
            url,
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if completed.returncode:
            details = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"Browser PDF export failed ({completed.returncode}): {details}")
    return validate_pdf(output_pdf)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source HTML file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Destination PDF")
    parser.add_argument("--browser", type=Path, help="Chrome or Edge executable")
    args = parser.parse_args()

    browser = find_browser(args.browser)
    pages = render(args.input, args.output, browser)
    page_text = f", {pages} pages" if pages is not None else ""
    print(f"Created {args.output.resolve()}{page_text} using {browser.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
