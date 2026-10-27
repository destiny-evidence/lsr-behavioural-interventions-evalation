import csv
import sys
from collections import defaultdict
from pathlib import Path

MODIFIED, LINK, OUT_DIR = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

OUT_DIR.mkdir(parents=True, exist_ok=True)

with MODIFIED.open(encoding="utf-8", newline="") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

id_col = header.index("document_id")
header[id_col] = "effect_originalRow"
rows_by_source_id = {}
for row in rows:
    rows_by_source_id.setdefault(row[id_col], []).append(row)

with LINK.open(encoding="utf-8", newline="") as f:
    links = list(csv.DictReader(f))

source_ids_by_study = defaultdict(list)
for link in links:
    source_ids_by_study[int(link["document_id"])].append(link["effect_originalRow"])

written = 0
for document_id, source_ids in sorted(source_ids_by_study.items()):
    out_rows = [row for source_id in source_ids for row in rows_by_source_id[source_id]]
    out_path = OUT_DIR / f"effects_documentID_{document_id:03d}.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(out_rows)
    written += len(out_rows)

assert written == len(rows), f"wrote {written} effect rows, expected {len(rows)}"
print(f"wrote {len(source_ids_by_study)} files with {written} effect rows to {OUT_DIR}")
