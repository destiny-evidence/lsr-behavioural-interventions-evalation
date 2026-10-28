"""Randomly select studies that have a linked PDF from link_map.csv."""

import csv
import random

from living_review_interventions.utils.paths import find_project_root

BASE_DIR = find_project_root()
LINK_MAP = BASE_DIR / "src" / "living_review_interventions" / "link_map.csv"
OUTPUT = (
    BASE_DIR
    / "src"
    / "living_review_interventions"
    / "data-extraction-experiments"
    / "selection_exp1.csv"
)
N_SELECT = 10


def main() -> None:
    with LINK_MAP.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    with_pdf = [row for row in rows if row["file_path"].strip()]
    selected = random.sample(with_pdf, N_SELECT)

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["internal_ID", "external_ID", "name", "pdf_path", "md_file_path"]
        )
        for row in selected:
            writer.writerow(
                [
                    row["document_id"],
                    row["external_id"],
                    row["name"],
                    row["file_path"],
                    row["md_file_path"],
                ]
            )

    print(f"{len(with_pdf)} studies have a PDF path; wrote {len(selected)} to {OUTPUT}")


if __name__ == "__main__":
    main()
