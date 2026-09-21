"""
Extractor Registry for automatic format detection.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Type, Optional

from .base import BaseExtractor
from .csv_extractor import CSVExtractor
from .excel_extractor import ExcelExtractor
from .json_extractor import JSONExtractor
from .xml_extractor import XMLExtractor
from .text_extractor import TextExtractor

AVAILABLE_EXTRACTORS: List[Type[BaseExtractor]] = [
    CSVExtractor,
    ExcelExtractor,
    JSONExtractor,
    XMLExtractor,
    TextExtractor,
]


def get_extractor_for_file(file_path: str | Path) -> BaseExtractor:
    """Detects and instantiates the appropriate extractor for the file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    for extractor_cls in AVAILABLE_EXTRACTORS:
        if extractor_cls.can_handle(path):
            return extractor_cls()

    # Fallback to TextExtractor
    return TextExtractor()
