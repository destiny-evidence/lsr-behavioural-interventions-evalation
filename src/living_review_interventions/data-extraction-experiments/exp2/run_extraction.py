"""Run the extraction pipeline on every study in selected_studies.csv."""

import csv
import json
import shutil
from pathlib import Path

from deet.main_hierarchical import (
    run_predict_single_study,
    setup_console_logging,
)
from loguru import logger

setup_console_logging()

C_DIR = Path(__file__).resolve().parent

with (C_DIR / "selected_studies.csv").open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

for row in rows:
    external_id = row["external_ID"]
    config = {
        "study_type": "BehaviouralIntervention",
        "llm_model": "azure/gpt-5.6-luna",
        "max_tokens": 60000,
        "dspy_cache": False,
        "input_paths": [row["md_file_path"]],
        "external_id": external_id,
        "output_parent_dir": C_DIR.as_posix(),
        "export_csv": False,
        "export_xlsx": True,
        "export_json": False,
    }
    config_path = C_DIR / f"config_{external_id}.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    logger.info(f"--- Predicting study external_ID {external_id} ---")
    try:
        run_predict_single_study(str(config_path))
        # run_predict_single_study writes results to <output_parent_dir>/<md file stem>/
        study_dir = C_DIR / Path(row["md_file_path"]).stem
        shutil.move(str(config_path), study_dir / config_path.name)
    except Exception:
        logger.exception(f"Failed to process external_ID {external_id}, continuing")


# # create a folder with only a subset of markdown files to test batch processing
# SELECTION_DIR = Path(__file__).resolve().parent
# SELECTED_MD_DIR = BASE_DIR / "data" / SELECTION_DIR.name
#
# with (SELECTION_DIR / "selected_studies.csv").open(newline="", encoding="utf-8") as f:
#     for row in csv.DictReader(f):
#         SELECTED_MD_DIR.mkdir(parents=True, exist_ok=True)
#         shutil.copy2(row["md_file_path"], SELECTED_MD_DIR)
