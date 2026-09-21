"""
CSV and TSV extractor with automatic delimiter and encoding detection.
"""

from __future__ import annotations
import csv
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
from .base import BaseExtractor


class CSVExtractor(BaseExtractor):
    """Extractor for CSV, TSV, and delimited text files."""

    SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt"}

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        ext = file_path.suffix.lower()
        if ext in {".csv", ".tsv"}:
            return True
        if ext == ".txt":
            # Quick check if it looks like delimited file
            try:
                with open(file_path, "rb") as f:
                    chunk = f.read(1024)
                    return b"," in chunk or b";" in chunk or b"\t" in chunk
            except Exception:
                return False
        return False

    @staticmethod
    def _detect_encoding(file_path: Path) -> str:
        """Detects encoding between utf-8, utf-8-sig, cp1251, and latin1."""
        with open(file_path, "rb") as f:
            raw = f.read(4096)

        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"

        # Try UTF-8
        try:
            raw.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            pass

        # Try CP1251 (Russian / Eastern European)
        try:
            raw.decode("cp1251")
            return "cp1251"
        except UnicodeDecodeError:
            pass

        return "latin1"

    @staticmethod
    def _detect_delimiter(file_path: Path, encoding: str) -> str:
        """Sniffs delimiter between ',', ';', '\t', '|'."""
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            sample_lines = [f.readline() for _ in range(10)]

        sample_text = "".join(l for l in sample_lines if l.strip())
        if not sample_text:
            return ","

        try:
            dialect = csv.Sniffer().sniff(sample_text, delimiters=[",", ";", "\t", "|"])
            return dialect.delimiter
        except Exception:
            # Fallback heuristic: count frequencies
            counts = {
                ",": sample_text.count(","),
                ";": sample_text.count(";"),
                "\t": sample_text.count("\t"),
                "|": sample_text.count("|"),
            }
            best_delim = max(counts, key=counts.get)
            return best_delim if counts[best_delim] > 0 else ","

    def get_sample(
        self, file_path: Path, max_rows: int = 20
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        encoding = self._detect_encoding(file_path)
        delimiter = self._detect_delimiter(file_path, encoding)

        rows: List[Dict[str, Any]] = []
        headers: List[str] = []

        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                raw_headers = next(reader)
                headers = [h.strip() for h in raw_headers if h is not None]
            except StopIteration:
                return [], []

            for row in reader:
                if not row or not any(x.strip() for x in row):
                    continue
                row_dict = {}
                for idx, h in enumerate(headers):
                    val = row[idx].strip() if idx < len(row) else ""
                    row_dict[h] = val
                rows.append(row_dict)
                if len(rows) >= max_rows:
                    break

        return headers, rows

    def extract_chunks(
        self, file_path: Path, chunk_size: int = 1000
    ) -> Iterator[List[Dict[str, Any]]]:
        encoding = self._detect_encoding(file_path)
        delimiter = self._detect_delimiter(file_path, encoding)

        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                raw_headers = next(reader)
                headers = [h.strip() for h in raw_headers if h is not None]
            except StopIteration:
                return

            chunk: List[Dict[str, Any]] = []
            for row in reader:
                if not row or not any(x.strip() for x in row):
                    continue
                row_dict = {}
                for idx, h in enumerate(headers):
                    val = row[idx].strip() if idx < len(row) else ""
                    row_dict[h] = val
                chunk.append(row_dict)
                if len(chunk) >= chunk_size:
                    yield chunk
                    chunk = []

            if chunk:
                yield chunk
