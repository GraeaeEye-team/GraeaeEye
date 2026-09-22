"""
JSON and JSONL extractor for structured documents.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
from .base import BaseExtractor


class JSONExtractor(BaseExtractor):
    """Extractor for JSON and JSONL documents."""

    SUPPORTED_EXTENSIONS = {".json", ".jsonl"}

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        return file_path.suffix.lower() in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def _read_records(cls, file_path: Path) -> List[Dict[str, Any]]:
        """Reads JSON or JSONL into a list of dictionaries."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            first_char = f.read(1).strip()
            f.seek(0)

            # JSONL check
            if file_path.suffix.lower() == ".jsonl" or first_char not in ("[", "{"):
                records = []
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                return records

            # Standard JSON
            try:
                data = json.load(f)
            except Exception:
                return []

            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            elif isinstance(data, dict):
                # Search for common list keys
                for key in ["data", "records", "items", "rows", "invoices", "transactions", "businesses"]:
                    if key in data and isinstance(data[key], list):
                        return [r for r in data[key] if isinstance(r, dict)]
                # If it's a single record object
                return [data]

        return []

    def get_sample(
        self, file_path: Path, max_rows: int = 20
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        records = self._read_records(file_path)
        if not records:
            return [], []

        # Aggregate headers across records
        headers_set = {}
        sample = records[:max_rows]
        for r in sample:
            for k in r.keys():
                headers_set[k] = True
        headers = list(headers_set.keys())

        # Flatten any simple values to string or numeric
        normalized_sample = []
        for r in sample:
            row_dict = {}
            for h in headers:
                val = r.get(h)
                if isinstance(val, (dict, list)):
                    row_dict[h] = json.dumps(val, ensure_ascii=False)
                elif val is not None:
                    row_dict[h] = str(val)
                else:
                    row_dict[h] = ""
            normalized_sample.append(row_dict)

        return headers, normalized_sample

    def extract_chunks(
        self, file_path: Path, chunk_size: int = 1000
    ) -> Iterator[List[Dict[str, Any]]]:
        records = self._read_records(file_path)
        if not records:
            return

        headers_set = {}
        for r in records[:50]:
            for k in r.keys():
                headers_set[k] = True
        headers = list(headers_set.keys())

        chunk: List[Dict[str, Any]] = []
        for r in records:
            row_dict = {}
            for h in headers:
                val = r.get(h)
                if isinstance(val, (dict, list)):
                    row_dict[h] = json.dumps(val, ensure_ascii=False)
                elif val is not None:
                    row_dict[h] = str(val)
                else:
                    row_dict[h] = ""
            chunk.append(row_dict)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []

        if chunk:
            yield chunk
