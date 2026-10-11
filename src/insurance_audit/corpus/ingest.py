"""Build candidate articles from explicitly selected local extraction artifacts."""

import hashlib
import json
import re
import shutil
from pathlib import Path

MARK = re.compile(r"^\s*(第[〇零一二三四五六七八九十百千]+条)\s*(.*)$")
CHAPTER = re.compile(r"^\s*第[〇零一二三四五六七八九十百千]+[章节]")
FOOTER = re.compile(
    r"^(?:手机扫一扫打开此页|https://www\.nfra\.gov\.cn/cn/view/pages/ItemDetail\.html\?"
    r".*|中国人民银行.*有关负责人就《金融产品网络营销管理办法》答记者问)$"
)
DIGITS = dict(zip("〇零一二三四五六七八九", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def confined(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path outside project root: {relative}")
    return path


def article_number(label: str) -> int:
    total = digit = 0
    for character in label.removeprefix("第").removesuffix("条"):
        if character in DIGITS:
            digit = DIGITS[character]
        elif character in "十百千":
            total += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[character]
            digit = 0
        else:
            raise ValueError(f"Invalid article label: {label}")
    return total + digit


def parse_units(units: list[str], *, pdf: bool = False) -> list[dict]:
    rows = []
    chapter = ""
    for unit_index, unit in enumerate(units):
        for line_index, raw in enumerate(unit.splitlines(), 1):
            line = raw.strip()
            if not line:
                continue
            if CHAPTER.match(line):
                chapter = line
                continue  # Headings belong to metadata, never to the preceding article.
            if pdf and FOOTER.match(line):
                continue  # Known webpage navigation, retained in the original extraction.
            locator = {"line_start": line_index, "line_end": line_index}
            key = "page" if pdf else "paragraph"
            position = unit_index + 1 if pdf else unit_index
            locator.update({f"{key}_start": position, f"{key}_end": position})
            match = MARK.match(line)
            if match:
                rows.append(
                    {
                        "label": match[1],
                        "parts": [match[2]] if match[2] else [],
                        "chapter": chapter,
                        "locator": locator,
                    }
                )
            elif rows:
                rows[-1]["parts"].append(line)
                rows[-1]["locator"][f"{key}_end"] = position
                rows[-1]["locator"]["line_end"] = line_index
    numbers = [article_number(row["label"]) for row in rows]
    if not numbers or numbers != list(range(1, len(numbers) + 1)):
        raise ValueError(f"Article numbering missing, duplicated or unordered: {numbers}")
    return rows


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )


def snapshot_manifest(root: Path, output: Path, ruleset_id: str) -> dict:
    existing = output / "manifest.json"
    if (
        existing.is_file()
        and json.loads(existing.read_text(encoding="utf-8")).get("publication_status")
        == "published"
    ):
        raise ValueError("Published snapshot manifest is immutable")
    names = (
        "documents.jsonl",
        "articles.jsonl",
        "chunks.jsonl",
        "rule_cards.jsonl",
        "article-review-ledger.jsonl",
        "review.json",
    )
    docs = [
        json.loads(line)
        for line in (output / "documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = {
        "schema_version": "1.0",
        "ruleset_id": ruleset_id,
        "ruleset_mode": "official_snapshot",
        "publication_status": "candidate",
        "scope": "Explicitly selected locally provided regulations",
        "excluded_sources": [
            {
                "document_id": s["document_id"],
                "reason": s.get("workflow_status", s.get("membership", "not_selected")),
            }
            for s in json.loads((root / "data/sources/catalog.json").read_text(encoding="utf-8"))[
                "sources"
            ]
            if s["document_id"] not in {d["document_id"] for d in docs}
        ],
        "sources": [
            {
                k: d[k]
                for k in (
                    "document_id",
                    "source_path",
                    "source_sha256",
                    "snapshot_source_path",
                    "extraction_sha256",
                    "snapshot_extraction_path",
                    "document_status",
                )
            }
            for d in docs
        ],
        "artifacts": {name: sha256(output / name) for name in names if (output / name).is_file()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_candidate(root: Path, source_manifest: Path, ruleset_id: str) -> dict:
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    if manifest["ruleset_id"] != ruleset_id:
        raise ValueError("Source manifest ruleset mismatch")
    output = confined(root, f"data/corpus/{ruleset_id}")
    if (output / "manifest.json").is_file():
        previous = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        if previous.get("publication_status") == "published":
            raise ValueError("Published snapshots cannot be overwritten")
    catalog = json.loads((root / "data/sources/catalog.json").read_text(encoding="utf-8"))
    registered = {doc["document_id"]: doc for doc in catalog["sources"]}
    documents, articles = [], []
    copies = []
    for doc in manifest["documents"]:
        if registered.get(doc["document_id"], {}).get("membership") != "include":
            raise ValueError(f"Source not explicitly included: {doc['document_id']}")
        for field in ("source_path", "source_sha256", "document_status", "title"):
            if doc.get(field) != registered[doc["document_id"]].get(field):
                raise ValueError(f"Source catalog mismatch: {doc['document_id']} {field}")
        source = confined(root, doc["source_path"])
        if sha256(source) != doc["source_sha256"]:
            raise ValueError(f"Source hash mismatch: {doc['document_id']}")
        pdf = source.suffix.lower() == ".pdf"
        extract = (
            root / "data/extracted" / (source.stem + (".pages.json" if pdf else ".paragraphs.json"))
        )
        units = json.loads(extract.read_text(encoding="utf-8"))
        parsed = parse_units(units, pdf=pdf)
        snapshot_source = output / "source-files" / source.name
        snapshot_extract = output / "extracted-files" / extract.name
        copies.extend([(source, snapshot_source), (extract, snapshot_extract)])
        extraction = doc.get("extraction", {})
        documents.append(
            {
                **{
                    k: doc[k]
                    for k in (
                        "document_id",
                        "title",
                        "source_path",
                        "source_sha256",
                        "document_status",
                        "published_on",
                        "effective_on",
                        "official_source_url",
                    )
                },
                "ruleset_id": ruleset_id,
                "extraction_method": doc.get("extraction_method", extraction.get("extractor")),
                "extraction_version": doc.get("extraction_version", extraction.get("version")),
                "extraction_path": extract.relative_to(root).as_posix(),
                "extraction_sha256": sha256(extract),
                "extraction_verified": "structural_only",
                "source_type": registered[doc["document_id"]]["source_type"],
                "valid_from": doc["effective_on"],
                "valid_to": None,
                "snapshot_source_path": snapshot_source.relative_to(root).as_posix(),
                "snapshot_extraction_path": snapshot_extract.relative_to(root).as_posix(),
                "legal_text_verified": False,
            }
        )
        for row in parsed:
            text = "\n".join(row["parts"]).strip()
            if not text:
                raise ValueError(f"Empty article: {doc['document_id']} {row['label']}")
            number = article_number(row["label"])
            articles.append(
                {
                    "article_id": f"{doc['document_id']}::art_{number:03d}",
                    "document_id": doc["document_id"],
                    "article_no": number,
                    "article_label": row["label"],
                    "chapter": row["chapter"],
                    "original_text": text,
                    "normalized_text": " ".join(text.split()),
                    "source_locator": {
                        "kind": "PDF page and extracted line" if pdf else "WPS COM paragraph index",
                        **row["locator"],
                    },
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "verified": False,
                }
            )
    # Stage all source checks before writing candidate artifacts.
    output.mkdir(parents=True, exist_ok=True)
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    write_jsonl(output / "documents.jsonl", documents)
    write_jsonl(output / "articles.jsonl", articles)
    write_jsonl(
        output / "chunks.jsonl",
        [
            {
                "chunk_id": a["article_id"],
                "article_id": a["article_id"],
                "document_id": a["document_id"],
                "text": a["original_text"],
                "chapter": a["chapter"],
            }
            for a in articles
        ],
    )
    summary = {
        "ruleset_id": ruleset_id,
        "document_count": len(documents),
        "article_count": len(articles),
        "by_document": {
            d["document_id"]: sum(a["document_id"] == d["document_id"] for a in articles)
            for d in documents
        },
        "all_text_nonempty": True,
        "article_text_verified": False,
        "ruleset_published": False,
    }
    (output / "parse-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    refresh_ledger(root, output, ruleset_id)
    return summary


def refresh_ledger(root: Path, output: Path, ruleset_id: str) -> None:
    cards_path = output / "rule_cards.jsonl"
    cards = (
        [
            json.loads(line)
            for line in cards_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if cards_path.is_file()
        else []
    )
    articles = [
        json.loads(line)
        for line in (output / "articles.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ledger = [
        {
            "article_id": a["article_id"],
            "ruleset_id": ruleset_id,
            "rule_ids": sorted(c["rule_id"] for c in cards if a["article_id"] in c["article_ids"]),
            "classification_status": "pending_review",
            "checkability": None,
            "exclusion_reason": None,
            "verified": False,
        }
        for a in articles
    ]
    write_jsonl(output / "article-review-ledger.jsonl", ledger)
    snapshot_manifest(root, output, ruleset_id)
