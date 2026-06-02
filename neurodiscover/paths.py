"""Shared paths for the neurodiscover data layer."""
import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def default_db_path() -> str:
    """SQLite file path. Override with NEURODISCOVER_DB env var."""
    return os.environ.get("NEURODISCOVER_DB", os.path.join(PACKAGE_DIR, "neurodiscover.db"))


def schema_path() -> str:
    return os.path.join(PACKAGE_DIR, "schema.sql")


def seed_path() -> str:
    return os.path.join(PACKAGE_DIR, "seed_data.json")
