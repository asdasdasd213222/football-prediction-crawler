"""Canonical hashing for normalized business JSON."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode a JSON-compatible mapping deterministically as UTF-8 bytes."""
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("Business data must be JSON-compatible.") from error


def fingerprint_business_data(data: Mapping[str, Any]) -> str:
    """Return the SHA-256 fingerprint of canonical normalized business data."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()
