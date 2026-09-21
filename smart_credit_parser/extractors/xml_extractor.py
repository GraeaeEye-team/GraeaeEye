"""
XML extractor for financial, 1C and banking XML documents.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple
import xml.etree.ElementTree as ET
from .base import BaseExtractor


class XMLExtractor(BaseExtractor):
    """Extractor for structured XML documents."""

    SUPPORTED_EXTENSIONS = {".xml"}

    @classmethod
    def can_handle(cls, file_path: Path) -> bool:
        return file_path.suffix.lower() in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def _parse_xml_to_records(cls, file_path: Path) -> List[Dict[str, Any]]:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except Exception:
            return []

        # Find repeating child elements
        # Strategy: inspect child tags under root or grandchildren
        tag_counts: Dict[str, List[ET.Element]] = {}
        for child in root:
            # Strip namespace prefix if present e.g. {urn:iso:...}tag
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            tag_counts.setdefault(tag, []).append(child)

        record_elements: List[ET.Element] = []
        if tag_counts:
            # Pick the tag with most occurrences
            most_frequent_tag = max(tag_counts, key=lambda k: len(tag_counts[k]))
            if len(tag_counts[most_frequent_tag]) > 1:
                record_elements = tag_counts[most_frequent_tag]

        # If direct children aren't repeating, search 1 level deeper
        if not record_elements:
            for child in root:
                inner_tag_counts: Dict[str, List[ET.Element]] = {}
                for grandchild in child:
                    gtag = grandchild.tag.split("}")[-1] if "}" in grandchild.tag else grandchild.tag
                    inner_tag_counts.setdefault(gtag, []).append(grandchild)
                if inner_tag_counts:
                    best_inner = max(inner_tag_counts, key=lambda k: len(inner_tag_counts[k]))
                    if len(inner_tag_counts[best_inner]) > 1:
                        record_elements.extend(inner_tag_counts[best_inner])

        # If still no repeating, treat direct children as fields of a single record
        if not record_elements:
            single_record = {}
            for child in root:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                single_record[tag] = (child.text or "").strip()
            return [single_record] if single_record else []

        # Flatten each record element
        records = []
        for elem in record_elements:
            row: Dict[str, Any] = {}
            # Include XML attributes
            for attr_k, attr_v in elem.attrib.items():
                row[attr_k] = attr_v
            # Include child tags
            for child in elem:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                row[ctag] = (child.text or "").strip()
            records.append(row)

        return records

    def get_sample(
        self, file_path: Path, max_rows: int = 20
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        records = self._parse_xml_to_records(file_path)
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
        records = self._parse_xml_to_records(file_path)
        if not records:
            return

        for i in range(0, len(records), chunk_size):
            yield records[i : i + chunk_size]
