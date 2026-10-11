"""Parse the selected official snapshot into stable article records.

This script preserves extracted text and provenance. It does not assert legal review.
"""
import hashlib
import json
import re
from pathlib import Path

from build_extraction_registry import build_registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/corpus/official-v1-2026-10-11"
OUT.mkdir(parents=True, exist_ok=True)
MARK = re.compile(r"^\s*(第[〇零一二三四五六七八九十百千]+条)\s*(.*)$")
CHAPTER = re.compile(r"^\s*第[一二三四五六七八九十百零]+章")
manifest = json.loads((ROOT / "data/extracted/official-source-manifest.json").read_text(encoding="utf-8"))
DOCS = manifest["documents"]

def rows_from_doc(paragraphs):
    rows=[]; chapter=""
    for i, raw in enumerate(paragraphs):
        for line_no, part in enumerate(raw.splitlines(), 1):
            line=part.strip()
            if not line: continue
            if CHAPTER.match(line): chapter=line
            m=MARK.match(line)
            if m:
                rows.append({"label":m.group(1),"parts":[m.group(2).strip()] if m.group(2).strip() else [],"chapter":chapter,"locator":{"paragraph_start":i,"paragraph_end":i,"line_start":line_no,"line_end":line_no}})
            elif rows:
                rows[-1]["parts"].append(line); rows[-1]["locator"]["paragraph_end"]=i; rows[-1]["locator"]["line_end"]=line_no
    return rows

def rows_from_pdf(pages):
    rows=[]; chapter=""
    for page_no, page in enumerate(pages,1):
        for line_no, raw in enumerate(page.splitlines(),1):
            line=raw.strip()
            if not line: continue
            if CHAPTER.match(line): chapter=line
            m=MARK.match(line)
            if m:
                rows.append({"label":m.group(1),"parts":[m.group(2).strip()] if m.group(2).strip() else [],"chapter":chapter,"locator":{"page_start":page_no,"line_start":line_no,"page_end":page_no,"line_end":line_no}})
            elif rows:
                rows[-1]["parts"].append(line)
                rows[-1]["locator"]["page_end"]=page_no
                rows[-1]["locator"]["line_end"]=line_no
    return rows

articles=[]; documents=[]
for doc in DOCS:
    doc_id=doc["document_id"]; title=doc["title"]; source=doc["source_path"]
    source_file=ROOT/source
    extract_file=(f"{title}.pages.json" if source_file.suffix.lower()==".pdf"
                  else f"{title}.paragraphs.json")
    locator_kind="PDF page and extracted line" if source_file.suffix.lower()==".pdf" else "WPS COM paragraph index"
    extracted=ROOT/"data/extracted"/extract_file
    parsed=json.loads(extracted.read_text(encoding="utf-8"))
    rows=rows_from_pdf(parsed) if source_file.suffix.lower()==".pdf" else rows_from_doc(parsed)
    documents.append({"document_id":doc_id,"title":title,"source_path":source,"source_sha256":doc["source_sha256"],"document_status":doc["document_status"],"published_on":doc["published_on"],"effective_on":doc["effective_on"],"ruleset_id":"official-v1-2026-10-11","official_source_url":doc["official_source_url"],"extraction_method":"PyMuPDF page.get_text(sort=True)" if source_file.suffix.lower()==".pdf" else "WPS COM Content.Text","extraction_verified":"structural_only","legal_text_verified":False})
    for idx,row in enumerate(rows,1):
        text="\n".join(part for part in row["parts"] if part).strip()
        normalized=" ".join(text.split())
        article_id=f"{doc_id}::art_{idx:03d}"
        articles.append({"article_id":article_id,"document_id":doc_id,"article_no":idx,"article_label":row["label"],"chapter":row["chapter"],"original_text":text,"normalized_text":normalized,"source_locator":{"kind":locator_kind,**row["locator"]},"text_sha256":hashlib.sha256(text.encode()).hexdigest(),"verified":False})

(OUT/"documents.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in documents),encoding="utf-8")
(OUT/"articles.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in articles),encoding="utf-8")
(OUT/"chunks.jsonl").write_text("".join(json.dumps({"chunk_id":a["article_id"],"article_id":a["article_id"],"document_id":a["document_id"],"text":a["original_text"],"chapter":a["chapter"]},ensure_ascii=False)+"\n" for a in articles),encoding="utf-8")
summary={"ruleset_id":"official-v1-2026-10-11","document_count":len(documents),"article_count":len(articles),"by_document":{d["document_id"]:sum(a["document_id"]==d["document_id"] for a in articles) for d in documents},"all_text_nonempty":all(a["original_text"] for a in articles),"article_text_verified":False,"ruleset_published":False}
(OUT/"parse-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
build_registry()
print(json.dumps(summary,ensure_ascii=False,indent=2))
