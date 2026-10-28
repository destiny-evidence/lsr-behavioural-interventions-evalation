"""Parse linked PDFs to markdown and record each markdown path in link_map.csv.

Each markdown file is written next to its PDF with the same stem. pdfminer is the
default parser. marker is only tried for PDFs that pdfminer fails on (e.g. no text
layer, or text failing the language check). Existing markdown files are kept.
"""

import csv
from pathlib import Path

from deet.processors.parser import DocumentParser, MarkerParser, PdfminerParser
from loguru import logger

from living_review_interventions.utils.paths import find_project_root

BASE_DIR = find_project_root()
LINK_MAP = BASE_DIR / "src" / "living_review_interventions" / "link_map.csv"
REPORT = BASE_DIR / "src" / "living_review_interventions" / "parse_report.csv"
MD_COLUMN = "md_file_path"

document_parser = DocumentParser()


def parse_pdf(pdf: Path, md: Path) -> str:
    """Write `md` from `pdf` and return the name of the parser that succeeded."""
    try:
        document_parser(input_=pdf, out_path=md, parser=PdfminerParser)
        return PdfminerParser.name
    except Exception as exc:
        logger.warning(f"pdfminer failed on {pdf.name} ({exc}); trying marker")

    document_parser(input_=pdf, out_path=md, parser=MarkerParser)
    return MarkerParser.name


def main() -> None:
    with LINK_MAP.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if MD_COLUMN not in fields:
        fields.insert(fields.index("file_path") + 1, MD_COLUMN)

    report = []
    for row in rows:
        pdf_path = row["file_path"].strip()
        if not pdf_path:
            row[MD_COLUMN] = ""
            continue

        pdf = Path(pdf_path)
        md = pdf.with_suffix(".md")
        row[MD_COLUMN] = str(md)

        if md.exists():
            report.append([row["document_id"], pdf.name, "", "exists"])
            continue

        try:
            parser_name = parse_pdf(pdf, md)
            report.append([row["document_id"], pdf.name, parser_name, "parsed"])
        except Exception as exc:
            logger.error(f"could not parse {pdf.name}: {exc}")
            report.append([row["document_id"], pdf.name, "", f"failed: {exc}"])

    with LINK_MAP.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with REPORT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["document_id", "pdf", "parser", "status"])
        writer.writerows(report)

    statuses = [r[3] for r in report]
    print(
        f"{len(report)} PDFs: {statuses.count('parsed')} parsed, "
        f"{statuses.count('exists')} already had markdown, "
        f"{sum(s.startswith('failed') for s in statuses)} failed. "
        f"Report: {REPORT}"
    )


if __name__ == "__main__":
    main()
