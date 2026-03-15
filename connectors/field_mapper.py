"""
connectors/field_mapper.py

Field mapping and data quality scoring for Huckleberry connectors.

Every CRM stores the same concepts with different field names:
  Zoho:        Lead_Source, Stage, Amount, Closing_Date
  Salesforce:  LeadSource, StageName, Amount, CloseDate
  HubSpot:     deal_stage, amount, closedate

The FieldMapper takes a customer-specific mapping configuration
and a raw source record and produces a canonical dict with
standardised field names.

It also computes data_quality_score — the fraction of required
fields that are present and non-null. This score feeds the
SignalReliability engine.

Design:

  Mapping config is a dict of canonical_field -> source_field_path.
  Paths support dot notation for nested access:
    "region": "Account.BillingState"
    "rep_id": "Owner.email"

  Required fields are defined per event type.
  Optional fields that are missing contribute 0 to the quality score.
  Required fields that are missing lower the quality score.

  data_quality_score = present_required / total_required
  Range: 0.00 to 1.00

  All field access is safe — missing paths return None, never raise.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


# Required fields per canonical event type
REQUIRED_FIELDS_BY_EVENT_TYPE: dict[str, list[str]] = {
    "lead_created":     ["occurred_at", "rep_id", "region"],
    "opp_opened":       ["occurred_at", "rep_id", "region", "deal_value"],
    "quote_issued":     ["occurred_at", "rep_id", "deal_value"],
    "quote_revised":    ["occurred_at", "rep_id", "deal_value"],
    "contact_touched":  ["occurred_at", "rep_id"],
    "stage_changed":    ["occurred_at", "rep_id", "stage_from", "stage_to"],
    "deal_won":         ["occurred_at", "rep_id", "deal_value"],
    "deal_lost":        ["occurred_at", "rep_id"],
}

# Required fields for operational metrics
REQUIRED_METRIC_FIELDS: list[str] = [
    "metric_type", "facility", "period_date", "value", "unit"
]


class FieldMapper:
    """
    Maps source system fields to Huckleberry canonical fields.

    One FieldMapper instance per connector type + customer combination.
    The mapping_config is loaded from the customer's configuration
    in Secrets Manager or the onboarding config table.

    Args:
        mapping_config: dict mapping canonical_field -> source_field_path
        stage_mapping:  dict mapping source stage names to canonical stage names
        region_mapping: dict mapping source region/territory to canonical region
        product_line_mapping: dict mapping source product to canonical product_line
    """

    def __init__(
        self,
        mapping_config: dict[str, str],
        stage_mapping: Optional[dict[str, str]] = None,
        region_mapping: Optional[dict[str, str]] = None,
        product_line_mapping: Optional[dict[str, str]] = None,
    ) -> None:
        self.mapping_config = mapping_config
        self.stage_mapping = stage_mapping or {}
        self.region_mapping = region_mapping or {}
        self.product_line_mapping = product_line_mapping or {}

    def map_commercial_event(
        self,
        raw_record: dict[str, Any],
        event_type: str,
    ) -> tuple[dict[str, Any], float]:
        """
        Map a raw CRM record to canonical CommercialEvent fields.

        Returns:
            (canonical_dict, data_quality_score)
            data_quality_score: 0.00 to 1.00
        """
        canonical: dict[str, Any] = {}

        # Map all configured fields
        for canonical_field, source_path in self.mapping_config.items():
            value = self._get_nested(raw_record, source_path)
            if value is not None:
                canonical[canonical_field] = value

        # Apply lookup table mappings
        if "stage_from" in canonical and canonical["stage_from"]:
            canonical["stage_from"] = self.stage_mapping.get(
                str(canonical["stage_from"]), str(canonical["stage_from"])
            )
        if "stage_to" in canonical and canonical["stage_to"]:
            canonical["stage_to"] = self.stage_mapping.get(
                str(canonical["stage_to"]), str(canonical["stage_to"])
            )
        if "region" in canonical and canonical["region"]:
            canonical["region"] = self.region_mapping.get(
                str(canonical["region"]), str(canonical["region"])
            )
        if "product_line" in canonical and canonical["product_line"]:
            canonical["product_line"] = self.product_line_mapping.get(
                str(canonical["product_line"]), str(canonical["product_line"])
            )

        # Coerce types
        canonical = self._coerce_commercial_event_types(canonical)

        # Compute quality score
        required_fields = REQUIRED_FIELDS_BY_EVENT_TYPE.get(event_type, [])
        quality_score = self._compute_quality_score(canonical, required_fields)

        canonical["data_quality_score"] = Decimal(str(round(quality_score, 2)))

        return canonical, quality_score

    def map_operational_metric(
        self,
        raw_record: dict[str, Any],
        customer_id: Any,
        source_system: str,
    ) -> tuple[dict[str, Any], float]:
        """
        Map a raw ERP record to canonical OperationalMetric fields.

        Returns:
            (canonical_dict, data_quality_score)
        """
        canonical: dict[str, Any] = {}

        for canonical_field, source_path in self.mapping_config.items():
            value = self._get_nested(raw_record, source_path)
            if value is not None:
                canonical[canonical_field] = value

        canonical = self._coerce_metric_types(canonical)

        # Compute dedup_key for aggregate record identification
        canonical["dedup_key"] = self._compute_dedup_key(
            customer_id=str(customer_id),
            source_system=source_system,
            metric_type=str(canonical.get("metric_type", "")),
            facility=str(canonical.get("facility", "")),
            period_date=str(canonical.get("period_date", "")),
        )

        quality_score = self._compute_quality_score(
            canonical, REQUIRED_METRIC_FIELDS
        )

        return canonical, quality_score

    def _get_nested(self, record: dict[str, Any], path: str) -> Any:
        """
        Safely retrieve a value from a nested dict using dot-notation path.
        Returns None if any part of the path is missing.

        Examples:
            _get_nested(record, "Owner.email") -> "john@example.com"
            _get_nested(record, "Amount") -> 45000.0
            _get_nested(record, "Account.BillingState") -> "GA"
        """
        if not path or not record:
            return None

        parts = path.split(".")
        current = record

        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None

        return current if current != "" else None

    def _compute_quality_score(
        self,
        canonical: dict[str, Any],
        required_fields: list[str],
    ) -> float:
        """
        Compute data quality score as fraction of required fields present.
        """
        if not required_fields:
            return 1.0

        present = sum(
            1 for f in required_fields
            if canonical.get(f) is not None
        )
        return present / len(required_fields)

    def _compute_dedup_key(
        self,
        customer_id: str,
        source_system: str,
        metric_type: str,
        facility: str,
        period_date: str,
    ) -> str:
        """
        Compute SHA-256 dedup key for aggregate metric records.
        Stable across reruns — same inputs always produce same key.
        """
        raw = f"{customer_id}:{source_system}:{metric_type}:{facility}:{period_date}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _coerce_commercial_event_types(
        self, canonical: dict[str, Any]
    ) -> dict[str, Any]:
        """Coerce field values to expected Python types."""
        result = dict(canonical)

        # occurred_at must be timezone-aware datetime
        if "occurred_at" in result and result["occurred_at"] is not None:
            result["occurred_at"] = self._parse_datetime(result["occurred_at"])

        # deal_value must be Decimal
        if "deal_value" in result and result["deal_value"] is not None:
            result["deal_value"] = self._parse_decimal(result["deal_value"])

        # days_in_stage must be int
        if "days_in_stage" in result and result["days_in_stage"] is not None:
            try:
                result["days_in_stage"] = int(result["days_in_stage"])
            except (ValueError, TypeError):
                result["days_in_stage"] = None

        # data_quality_score must be Decimal
        if "data_quality_score" in result:
            result["data_quality_score"] = self._parse_decimal(
                result["data_quality_score"]
            )

        return result

    def _coerce_metric_types(
        self, canonical: dict[str, Any]
    ) -> dict[str, Any]:
        """Coerce metric field values to expected Python types."""
        result = dict(canonical)

        # period_date must be date
        if "period_date" in result and result["period_date"] is not None:
            result["period_date"] = self._parse_date(result["period_date"])

        # value must be Decimal
        if "value" in result and result["value"] is not None:
            result["value"] = self._parse_decimal(result["value"])

        return result

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse various datetime formats to timezone-aware datetime."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)

        if isinstance(value, str):
            # Try common formats
            formats = [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(value, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue

        return None

    def _parse_date(self, value: Any) -> Optional[date]:
        """Parse various date formats to date object."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            # Try YYYY-MM-DD first
            try:
                return date.fromisoformat(value[:10])
            except (ValueError, IndexError):
                pass
        return None

    def _parse_decimal(self, value: Any) -> Optional[Decimal]:
        """Parse numeric value to Decimal."""
        if value is None:
            return None
        try:
            # Remove currency symbols and commas
            if isinstance(value, str):
                value = re.sub(r"[,$£€]", "", value).strip()
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
