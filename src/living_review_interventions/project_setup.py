# Created by Lennart at 26/10/2026

from deet.data_models.project import DeetProject
from deet.processors.converter_register import SupportedImportFormat

from living_review_interventions.utils.paths import find_project_root

root = find_project_root()
if root is None:
    raise FileNotFoundError("pyproject.toml not found")
data_dir = root / "data"

project = DeetProject(
    name="lsr-bi",
    gold_standard_data_path=data_dir / "resources" / "lsr_data_2025-20250513_unique_studies.csv",
    gold_standard_data_format=SupportedImportFormat.GENERIC_CSV, # Replace this if you are using another import format
    pdf_dir=data_dir / "PDF"
)
project.setup()
