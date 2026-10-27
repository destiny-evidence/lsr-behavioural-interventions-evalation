# Created by Lennart at 19/10/2026
import re
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from living_review_interventions.utils.paths import find_project_root

root = find_project_root()
if root is None:
    raise FileNotFoundError("pyproject.toml not found")

p = root / "data" / "resources"


def split_numeric_text(
    df: pd.DataFrame, column: str, numeric_name: str, text_name: str
) -> pd.DataFrame:
    """Replace a column mixing integer codes and text with two columns."""
    as_text = df[column].astype("string").str.strip().replace("", pd.NA)
    is_numeric = as_text.str.fullmatch(r"\d+(\.0+)?").fillna(False).astype(bool)
    numeric = pd.to_numeric(as_text.where(is_numeric)).astype("Int64")
    text = as_text.where(as_text.notna() & ~is_numeric)

    idx = df.columns.get_loc(column)
    df = df.drop(columns=column)
    df.insert(idx, numeric_name, numeric)
    df.insert(idx + 1, text_name, text)
    return df


def to_iso_date(value: object) -> str | None:
    """
    Convert a date to ISO YYYY-MM-DD.

    Handles unix seconds, Excel serial numbers, and dd/mm/yyyy or dd.mm.yyyy. Ambiguous
    dates are read day-first; mm/dd is used only where day-first is impossible.
    """
    if pd.isna(value):
        return None
    text = re.sub(r"\.0$", "", str(value).strip())
    if re.fullmatch(r"\d{10}", text):
        return datetime.fromtimestamp(int(text), tz=UTC).date().isoformat()
    if re.fullmatch(r"\d{5}", text):
        excel_epoch = pd.Timestamp("1899-12-30")
        return (excel_epoch + pd.Timedelta(days=int(text))).date().isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if match:
        first, second, year = (int(g) for g in match.groups())
        for day, month in ((first, second), (second, first)):
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                continue
    msg = f"Unrecognised date: {value!r}"
    raise ValueError(msg)

df = pd.read_csv(p / "lsr_data_2025-20250513.csv")

# find case-insensitive duplicate column names
groups: dict[str, list[str]] = {}
for col in df.columns:
    groups.setdefault(str(col).lower(), []).append(col)

# a potential duplicate is confirmed only if its values match the first column
# of its group (Series.equals treats NaNs in the same position as equal)
confirmed = []
rename_columns = {"document title": "name", "Authors": "authorship", "document PY": "publication_year"}
for name, cols in groups.items():
    if len(cols) < 2:
        continue
    keep, *others = cols
    for other in others:
        if df[keep].equals(df[other]):
            print(f"confirmed duplicate: {other!r} == {keep!r}")
            confirmed.append(other)
        else:
            print(f"name clash but different values: {other!r} vs {keep!r}")
            rename_columns[df[other].name] = df[other].name + "_2"
df_stripped = df.drop(columns=confirmed)
df_stripped.rename(columns=rename_columns, inplace=True)

# entirely empty columns cannot be type-inferred by deet
empty_columns = [
    "ExclusionReasonLSR",
    "EffectSizeExclusion",
    "EffectSizeExlusionReason",
    "issuesResolvedDoubleChecking",
    "knownUnresolvableIssues",
]
df_stripped = df_stripped.drop(columns=empty_columns)

# missing-value codes -> NA
df_stripped = df_stripped.replace(["-999", "-888", -999, -888], np.nan)

# strip units, and treat "unclear" durations as NA
for col in ["baselineConsumption", "interventionDuration", "interventionTreatmentPeriod"]:
    values = df_stripped[col].astype("string").str.strip().replace("unclear", pd.NA)
    df_stripped[col] = values.str.replace(r"\s*(kWh/day|weeks)$", "", regex=True)

df_stripped = split_numeric_text(
    df_stripped, "significance_bound", "significance_bound_numeric", "significance_bound_text"
)
df_stripped = split_numeric_text(
    df_stripped, "effect test_tails", "effect test_tails_numeric", "effect test_tails_text"
)

# free-text notes move to AdditionalInterventionNotes; the flag becomes 1
ai = df_stripped["AdditionalIntervention"].astype("string").str.strip()
is_flag = ai.str.fullmatch(r"\d+(\.0+)?").fillna(False).astype(bool)
has_note = ai.notna() & ~is_flag
df_stripped["AdditionalIntervention"] = pd.to_numeric(ai.mask(has_note, "1")).astype("Int64")
idx = df_stripped.columns.get_loc("AdditionalIntervention")
df_stripped.insert(idx + 1, "AdditionalInterventionNotes", ai.where(has_note))

df_stripped["Notes_interventionType"] = df_stripped["Notes_interventionType"].replace(["0", 0], np.nan)
df_stripped["multicoded"] = df_stripped["multicoded"].replace([1, "1"], "single")
df_stripped["dateCodingCompleted"] = df_stripped["dateCodingCompleted"].map(to_iso_date)
# df_stripped.insert(loc=0, column="document_id", value=list(range(1, 1+len(df_stripped))))
# df.insert(loc=0, column="document_id", value=[math.prod(v.split('-')) for v in df['effectID']])


out = p / "lsr_data_2025-20250513_modified.csv"
df_stripped.to_csv(out, index=False)
print(f"dropped {len(confirmed)} columns, saved to {out}")

