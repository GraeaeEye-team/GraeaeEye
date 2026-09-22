"""
AI Schema Mapping Agent.
Maps raw input structures to database schema with validation, caching, retries, and confidence scoring.
"""

from __future__ import annotations
import json
from typing import Any, Dict, List, Optional

from ..schema.models import SchemaGraph
from .cache import MappingCache, TableMapping, ColumnMapping
from .client import BaseLLMClient, get_default_llm_client
from .prompt_templates import SYSTEM_MAPPING_PROMPT, USER_MAPPING_PROMPT_TEMPLATE
from .schema_serializer import SchemaSerializer
from ..pipeline.fast_path import FastPathDetector
from ..pipeline.sanitizer import SecuritySanitizer


class MappingAgent:
    """Orchestrates AI-based column and table mapping with fast-path, caching, and retry logic."""

    def __init__(
        self,
        schema: SchemaGraph,
        llm_client: Optional[BaseLLMClient] = None,
        cache: Optional[MappingCache] = None,
    ):
        self.schema = schema
        self.llm_client = llm_client or get_default_llm_client()
        self.cache = cache or MappingCache()

    def determine_mapping(
        self,
        headers: List[str],
        sample_rows: List[Dict[str, Any]],
        target_table_hint: Optional[str] = None,
        bypass_cache: bool = False,
    ) -> TableMapping:
        """
        Determines the table and column mapping for an incoming dataset.
        1. Checks Fast-Path (deterministic canonical match).
        2. Checks Mapping Cache.
        3. Queries LLM with retry loop if needed.
        """
        # 1. Check Fast-Path
        fast_path = FastPathDetector.detect_canonical_table(
            headers, self.schema, target_table_hint=target_table_hint
        )
        if fast_path:
            return fast_path

        # 2. Check Cache
        signature = MappingCache.compute_signature(headers, target_table_hint)
        if not bypass_cache:
            cached = self.cache.get(signature)
            if cached:
                return cached

        # 3. Build Prompt
        schema_desc = SchemaSerializer.serialize_schema(
            self.schema,
            filter_tables=[target_table_hint] if target_table_hint else None,
        )

        # Sanitize headers and sample rows to protect against prompt injection
        safe_headers = [SecuritySanitizer.sanitize_raw_string(h) for h in headers]
        safe_samples = [
            {k: SecuritySanitizer.sanitize_raw_string(str(v)) for k, v in r.items()}
            for r in sample_rows[:10]
        ]

        user_prompt = USER_MAPPING_PROMPT_TEMPLATE.format(
            schema_description=schema_desc,
            target_table_hint=target_table_hint or "Infer best target table from data",
            headers_json=json.dumps(safe_headers, ensure_ascii=False),
            sample_rows_json=json.dumps(safe_samples, ensure_ascii=False, indent=2),
        )

        # 4. LLM Query with Retry Loop (up to 2 retries)
        last_error = ""
        current_prompt = user_prompt
        for attempt in range(3):
            try:
                raw_response = self.llm_client.generate_mapping(
                    prompt=current_prompt,
                    system_instruction=SYSTEM_MAPPING_PROMPT,
                )
                # Parse JSON
                mapping_data = self._clean_and_parse_json(raw_response)
                table_mapping = self._validate_and_build_mapping(mapping_data)

                # Store in cache
                self.cache.put(signature, table_mapping)
                return table_mapping

            except Exception as e:
                last_error = str(e)
                # Prepare retry prompt with feedback
                current_prompt = (
                    f"{user_prompt}\n\n"
                    f"### PREVIOUS ATTEMPT FAILED WITH ERROR:\n{last_error}\n"
                    "Please correct the error and return ONLY valid JSON matching the schema."
                )

        # 5. If all attempts failed, construct fallback mapping
        return self._construct_fallback_mapping(headers, target_table_hint, error=last_error)

    @staticmethod
    def _clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
        """Strips markdown ```json blocks and parses JSON."""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        return json.loads(text)

    def _validate_and_build_mapping(self, data: Dict[str, Any]) -> TableMapping:
        """Validates that target table and columns exist in SchemaGraph."""
        target_tbl_name = data.get("target_table", "").strip()
        tbl = self.schema.get_table(target_tbl_name)
        if not tbl:
            raise ValueError(f"Target table '{target_tbl_name}' does not exist in schema.sql.")

        col_mappings: List[ColumnMapping] = []
        raw_mappings = data.get("mappings", [])
        for m in raw_mappings:
            src = m.get("source_column")
            tgt = m.get("target_column")
            if not src or not tgt:
                continue

            target_col = tbl.get_column(tgt)
            if not target_col:
                # Disallow hallucinated target columns
                continue

            conf = float(m.get("confidence", 0.8))
            reason = m.get("reasoning", "")
            col_mappings.append(
                ColumnMapping(
                    source_column=src,
                    target_column=target_col.name,
                    confidence=conf,
                    reasoning=reason,
                )
            )

        # Unmapped required columns check
        mapped_targets = {cm.target_column.lower() for cm in col_mappings}
        unmapped_req = [
            rc for rc in tbl.required_columns() if rc.lower() not in mapped_targets
        ]

        return TableMapping(
            target_table=tbl.name,
            column_mappings=col_mappings,
            unmapped_source_columns=data.get("unmapped_source_columns", []),
            unmapped_required_columns=unmapped_req,
        )

    def _construct_fallback_mapping(
        self, headers: List[str], target_table_hint: Optional[str], error: str
    ) -> TableMapping:
        target_tbl = target_table_hint or "businesses"
        tbl = self.schema.get_table(target_tbl)
        req = tbl.required_columns() if tbl else []
        return TableMapping(
            target_table=target_tbl,
            column_mappings=[],
            unmapped_source_columns=headers,
            unmapped_required_columns=req,
        )
