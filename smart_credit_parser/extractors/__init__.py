"""
Extractors module exports.
"""

from .base import BaseExtractor
from .csv_extractor import CSVExtractor
from .excel_extractor import ExcelExtractor
from .json_extractor import JSONExtractor
from .xml_extractor import XMLExtractor
from .text_extractor import TextExtractor
from .registry import get_extractor_for_file

__all__ = [
    "BaseExtractor",
    "CSVExtractor",
    "ExcelExtractor",
    "JSONExtractor",
    "XMLExtractor",
    "TextExtractor",
    "get_extractor_for_file",
]
