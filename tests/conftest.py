import os
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(
    os.getenv(
        "SCHEMA_PATH",
        str(ROOT_DIR / "schema.sql") if (ROOT_DIR / "schema.sql").exists() else r"c:\Users\skv1d\Downloads\schema.sql"
    )
)


@pytest.fixture(scope="session")
def default_schema_path() -> Path:
    return SCHEMA_PATH
