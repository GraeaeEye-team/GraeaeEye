"""
Base Extractor interface using Adapter pattern.
All format extractors inherit from BaseExtractor.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple, Optional


class BaseExtractor(ABC):
    """Abstract format extractor."""

    @classmethod
    @abstractmethod
    def can_handle(cls, file_path: Path) -> bool:
        """Determines if this extractor can parse the given file."""
        pass

    @abstractmethod
    def get_sample(
        self, file_path: Path, max_rows: int = 20
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Extracts column headers and a sample of rows for schema analysis.
        Returns: (headers, sample_rows)
        """
        pass

    @abstractmethod
    def extract_chunks(
        self, file_path: Path, chunk_size: int = 1000
    ) -> Iterator[List[Dict[str, Any]]]:
        """
        Streamingly extracts records in chunks of chunk_size.
        """
        pass

    def extract_all(self, file_path: Path) -> List[Dict[str, Any]]:
        """Extracts all rows in memory."""
        all_rows: List[Dict[str, Any]] = []
        for chunk in self.extract_chunks(file_path, chunk_size=5000):
            all_rows.extend(chunk)
        return all_rows
