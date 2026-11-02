"""Run the extraction pipeline on the first study of selected_studies.csv."""

import csv
import json
import os
import shutil
from pathlib import Path

from deet.main_hierarchical import (
    run_parse_pdfs,
    run_predict_batch,
    run_predict_single_study,
    setup_console_logging,
)

from living_review_interventions.utils.paths import find_project_root


BASE_DIR = find_project_root()
C_DIR = Path(__file__).resolve().parent

#load only path of first md file
with (C_DIR / "selected_studies.csv").open(newline="", encoding="utf-8") as f:
    row = next(csv.DictReader(f))
    md_path = row["md_file_path"]
    external_id = row["external_ID"]


config = {"study_type": "BehaviouralIntervention",
    "llm_model": "azure/gpt-5.6-luna",
    "max_tokens": 60000,
    "dspy_cache": False,
    "input_paths": [md_path],
    "external_id": external_id,
    "output_parent_dir": C_DIR.as_posix(),
    "export_csv": False,
    "export_xlsx": True,
    "export_json": False,
}
config_path = C_DIR / "demo_config.json"
config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


# # create a folder with only a subset of markdown files to test batch processing
# SELECTION_DIR = Path(__file__).resolve().parent
# SELECTED_MD_DIR = BASE_DIR / "data" / SELECTION_DIR.name
#
# with (SELECTION_DIR / "selected_studies.csv").open(newline="", encoding="utf-8") as f:
#     for row in csv.DictReader(f):
#         SELECTED_MD_DIR.mkdir(parents=True, exist_ok=True)
#         shutil.copy2(row["md_file_path"], SELECTED_MD_DIR)



setup_console_logging()
run_predict_single_study(str(config_path))
