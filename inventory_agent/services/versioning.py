"""Deterministic semantic-version allocation for generated capabilities."""

from __future__ import annotations

import re
from collections.abc import Iterable


SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def next_capability_version(requested: str, existing: Iterable[str]) -> str:
    """Use the requested version when newer, otherwise allocate the next patch."""

    requested_match = SEMVER.fullmatch(requested)
    parsed = [
        tuple(int(part) for part in match.groups())
        for value in existing
        if (match := SEMVER.fullmatch(str(value))) is not None
    ]
    if requested_match is None or not parsed:
        return requested
    requested_tuple = tuple(int(part) for part in requested_match.groups())
    newest = max(parsed)
    if requested_tuple > newest:
        return requested
    return f"{newest[0]}.{newest[1]}.{newest[2] + 1}"
