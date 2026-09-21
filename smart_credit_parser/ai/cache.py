"""
Caching layer for AI schema mappings.
Avoids redundant LLM invocations for recurring file structures and formats.
"""

from __future__ import annotations
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


from ..schema.models import ColumnMapping, TableMapping


class MappingCache:
    """In-memory and file-backed LRU cache for table mappings."""

    def __init__(self, cache_file: Optional[Path] = None):
        self._memory_cache: Dict[str, TableMapping] = {}
        self.cache_file = cache_file

    @staticmethod
    def compute_signature(headers: List[str], target_table_hint: Optional[str] = None) -> str:
        """Generates deterministic SHA-256 fingerprint for a list of headers and target hint."""
        normalized = [h.strip().lower() for h in headers]
        payload = f"{target_table_hint or ''}|{'|'.join(sorted(normalized))}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, signature: str) -> Optional[TableMapping]:
        return self._memory_cache.get(signature)

    def put(self, signature: str, mapping: TableMapping) -> None:
        self._memory_cache[signature] = mapping

    def clear(self) -> None:
        self._memory_cache.clear()
