"""Canonical access_type values and legacy mapping for evidence rows."""
from __future__ import annotations

VALID_ACCESS_TYPES = frozenset({
    "published_oa",
    "published_paywalled",
    "preprint",
    "error",
    "unknown",
})

# Legacy Europe PMC values → new canonical values
LEGACY_ACCESS_TYPE_MAP = {
    "open": "published_oa",
    "restricted": "published_paywalled",
}


def normalize_access_type(access_type: str | None) -> str:
    """Map legacy open/restricted to published_oa/published_paywalled."""
    if not access_type:
        return "unknown"
    at = access_type.strip()
    return LEGACY_ACCESS_TYPE_MAP.get(at, at)


def access_status_from_type(access_type: str | None) -> str:
    """Map access_type to backend access_status column."""
    at = normalize_access_type(access_type)
    mapping = {
        "published_oa": "open",
        "published_paywalled": "restricted",
        "preprint": "abstract_only",
        "error": "error",
        "unknown": "unknown",
    }
    return mapping.get(at, "abstract_only")
