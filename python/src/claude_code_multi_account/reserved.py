"""Reserved account names, from `spec/reserved.json` (a verbatim copy ships in the package)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path


def reserved_names(spec_path: str | Path | None = None) -> tuple[str, ...]:
    """Reserved names. With `spec_path`, read that `reserved.json` instead of the packaged copy."""
    if spec_path is not None:
        text = Path(spec_path).read_text(encoding="utf-8")
    else:
        text = resources.files(__package__).joinpath("reserved.json").read_text(encoding="utf-8")
    data = json.loads(text)
    return tuple(str(item["name"]) for item in data["names"])
