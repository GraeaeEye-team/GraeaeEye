"""
Text and PDF extractor for semi-structured text files and reports.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
from .base import BaseExtractor

try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


class TextExtractor(BaseExtractor):
    """Extractor for TXT, log, and PDF files."""

    SUPPORTED_EXTENSIONS = {".txt", ".log", ".pdf"}

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        return file_path.suffix.lower() in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def _extract_raw_text(cls, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            if not PYPDF_AVAILABLE:
                raise ImportError("pypdf is required to extract text from PDF files.")
            reader = pypdf.PdfReader(str(file_path))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n".join(pages)
        else:
            # Plain text / log
            for enc in ["utf-8", "cp1251", "latin1"]:
                try:
                    return file_path.read_text(encoding=enc)
                except UnicodeDecodeError:
                    continue
            return file_path.read_text(encoding="utf-8", errors="replace")

    @classmethod
    def _parse_text_to_records(cls, raw_text: str) -> List[Dict[str, Any]]:
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        if not lines:
            return []

        # 1. Try key-value blocks (separated by blank lines or multiple records)
        has_colon_kv = False
        for l in lines[:20]:
            if ":" in l:
                k, v = l.split(":", 1)
                if len(k.strip()) < 40:
                    has_colon_kv = True

        if has_colon_kv:
            records: List[Dict[str, Any]] = []
            curr_rec: Dict[str, Any] = {}
            for l in lines:
                if ":" in l:
                    parts = l.split(":", 1)
                    k = parts[0].strip()
                    v = parts[1].strip()
                    if k in curr_rec and curr_rec:
                        # New record started
                        records.append(curr_rec)
                        curr_rec = {k: v}
                    else:
                        curr_rec[k] = v
                elif l.startswith("---") or l.startswith("==="):
                    if curr_rec:
                        records.append(curr_rec)
                        curr_rec = {}
            if curr_rec:
                records.append(curr_rec)
            if records:
                return records

        # 2. Try whitespace-delimited tabular rows
        # Check if first line has multiple words separated by 2+ spaces or tabs
        first_line = lines[0]
        tokens = re.split(r"\s{2,}|\t", first_line)
        if len(tokens) >= 2:
            headers = [t.strip() for t in tokens if t.strip()]
            records = []
            for l in lines[1:]:
                row_tokens = re.split(r"\s{2,}|\t", l)
                if row_tokens:
                    row_dict = {}
                    for idx, h in enumerate(headers):
                        row_dict[h] = row_tokens[idx].strip() if idx < len(row_tokens) else ""
                    records.append(row_dict)
            if records:
                return records

        # 3. Fallback: single record with raw lines or full text
        return [{"raw_text": raw_text}]

    def get_sample(
        self, file_path: Path, max_rows: int = 20
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        raw_text = self._extract_raw_text(file_path)
        records = self._parse_text_to_records(raw_text)
        if not records:
            return [], []

        headers_set = {}
        sample = records[:max_rows]
        for r in sample:
            for k in r.keys():
                headers_set[k] = True
        headers = list(headers_set.keys())

        return headers, sample

    def extract_chunks(
        self, file_path: Path, chunk_size: int = 1000
    ) -> Iterator[List[Dict[str, Any]]]:
        raw_text = self._extract_raw_text(file_path)
        records = self._parse_text_to_records(raw_text)
        if not records:
            return

        for i in range(0, len(records), chunk_size):
            yield records[i : i + chunk_size]
