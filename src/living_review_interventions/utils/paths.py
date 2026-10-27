from pathlib import Path


def find_project_root(
    start: Path = Path(__file__), marker: str = "pyproject.toml"
) -> Path | None:
    """Return the nearest ancestor of `start` containing `marker`, or None."""
    for p in start.resolve().parents:
        if (p / marker).exists():
            return p
    return None
