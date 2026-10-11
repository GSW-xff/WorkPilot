from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def bundled_path(*parts: str) -> Path:
    """Return a resource path that works in a checkout and an installed wheel."""
    return PACKAGE_ROOT.joinpath(*parts)
