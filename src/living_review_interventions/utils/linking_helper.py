import csv
import sys
from pathlib import Path

LINK_MAP, UNIQUE_STUDIES = Path(sys.argv[1]), Path(sys.argv[2])
REPO_ROOT = Path(__file__).resolve().parents[2]

with UNIQUE_STUDIES.open(encoding="utf-8", newline="") as f:
    studies = {int(s["document_id"]): s for s in csv.DictReader(f)}

with LINK_MAP.open(encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = list(reader)

filled = 0
for row in rows:
    study = studies.get(int(row["external_id"]))
    if study is None or not study["pdf_path"]:
        row["file_path"] = ""
        continue
    if float(study["pdf_title_score"] or 0) != 1:
        row["file_path"] = ""
        continue
    row["file_path"] = str((REPO_ROOT / study["pdf_path"]).resolve())
    filled += 1

with LINK_MAP.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"filled {filled} of {len(rows)} file_path values in {LINK_MAP}")
