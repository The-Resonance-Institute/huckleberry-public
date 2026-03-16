"""
examples/custom_erp_example.py

Example connector showing how to build a custom ERP connector for Huckleberry.

This file demonstrates the full pattern for an ERP connector. Copy it,
rename it to your system (e.g. connectors/erp/epicor.py), implement the
two methods, register it in connectors/registry.py, and submit a PR.

The connector fetches two types of data from your ERP:
  1. Operational metrics  — production output, labor hours, inventory, costs
  2. Financial metrics    — revenue, backlog, budget vs actual

All data is returned as OperationalMetricRecord objects. The platform
handles storage, signal computation, and everything downstream.

Your connector is read-only. Never write back to the source system.

Credentials are loaded from environment variables or AWS Secrets Manager.
Never hardcode credentials in connector files.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from connectors.base import BaseERPConnector, OperationalMetricRecord

logger = logging.getLogger(__name__)

# Replace these with your system's actual API base URL and auth pattern
YOUR_SYSTEM_API_BASE = "https://api.yoursystem.com/v1"
REQUEST_TIMEOUT      = 30.0


class CustomERPConnector(BaseERPConnector):
    """
    Example ERP connector. Replace with your system's name and API details.

    To use this as a template:
    1. Replace CustomERPConnector with YourSystemConnector
    2. Update YOUR_SYSTEM_API_BASE with your API endpoint
    3. Implement _fetch_metrics_raw() to call your API
    4. Implement _normalize_metric() to map your fields to the canonical schema
    5. Implement _validate_credentials() to test connectivity
    6. Register in connectors/registry.py
    """

    @property
    def erp_type(self) -> str:
        # Return the identifier string for this connector.
        # This is what you'll use in registry.py and customer config.
        return "custom_erp_example"

    async def fetch_operational_metrics(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[OperationalMetricRecord]:
        """
        Fetch operational metrics from your ERP.

        Called by the platform every 30 minutes. Pass last_sync_at to your
        API as a date filter to fetch only new/updated records.

        Returns a list of OperationalMetricRecord objects.
        """
        raw_records = await self._fetch_metrics_raw(
            last_sync_at=last_sync_at,
            limit=limit,
        )

        records = []
        for raw in raw_records:
            try:
                record = self._normalize_metric(raw)
                if record is not None:
                    records.append(record)
            except Exception as e:
                logger.debug(f"Metric normalization error: {e}")

        logger.info(
            f"Fetched {len(records)} metrics from {self.erp_type}",
            extra={"customer": self.customer_slug},
        )
        return records

    async def _fetch_metrics_raw(
        self,
        last_sync_at: Optional[datetime],
        limit: int,
    ) -> list[dict]:
        """
        Fetch raw metric records from your ERP API.

        Replace this implementation with actual API calls to your system.
        The pattern below shows a typical REST API call with date filtering
        and pagination.
        """
        if not self._credentials:
            logger.warning(f"No credentials for {self.customer_slug}")
            return []

        all_records = []
        page = 1

        params = {"limit": min(100, limit)}
        if last_sync_at:
            # Adjust the param name to match your API's date filter field
            params["updated_after"] = last_sync_at.isoformat()

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            while True:
                params["page"] = page

                try:
                    response = await client.get(
                        f"{YOUR_SYSTEM_API_BASE}/metrics",
                        headers=self._get_headers(),
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"API fetch failed: {e}")
                    break

                # Adjust the response key to match your API's response shape
                records = data.get("items", data.get("data", data.get("results", [])))
                if not records:
                    break

                all_records.extend(records)

                # Stop if we have enough or no more pages
                if len(all_records) >= limit or not data.get("has_more", False):
                    break

                page += 1

        return all_records

    def _normalize_metric(self, raw: dict) -> Optional[OperationalMetricRecord]:
        """
        Normalize a raw API response dict to an OperationalMetricRecord.

        This is where you map your system's field names to the canonical schema.
        Return None for records that can't be normalized cleanly.

        Canonical metric_type values (use these exactly):
          Production:   units_produced, units_started, units_scrapped
          Labor:        labor_hours_worked, labor_hours_standard
          Capacity:     capacity_utilized_hours, capacity_available_hours
          Inventory:    inventory_units, inventory_value
          Cost:         material_cost_actual, material_cost_standard
          Financial:    revenue_actual, revenue_plan, backlog_value
          Maintenance:  unplanned_downtime_hours, pm_compliance_rate
        """
        # Extract the record ID from your API response
        # Adjust field names to match your system
        record_id = str(raw.get("id") or raw.get("record_id") or "")
        if not record_id:
            return None

        # Map your system's metric type to the canonical metric_type
        # Adjust this mapping to match your system's metric names
        metric_type_map = {
            "production_output":     "units_produced",
            "labor_hours":           "labor_hours_worked",
            "capacity_used":         "capacity_utilized_hours",
            "capacity_available":    "capacity_available_hours",
            "material_cost":         "material_cost_actual",
            "material_standard":     "material_cost_standard",
            "revenue":               "revenue_actual",
            "backlog":               "backlog_value",
            # Add your system's metric names here
        }

        source_metric_type = raw.get("metric_type") or raw.get("type") or ""
        canonical_type = metric_type_map.get(source_metric_type)

        if canonical_type is None:
            # Unknown metric type — skip it
            return None

        # Parse the value — use _safe_decimal() for safety
        value = self._safe_decimal(raw.get("value") or raw.get("amount"))
        if value is None:
            return None

        # Parse the period date — the date this metric covers
        period_date = self._safe_datetime(
            raw.get("period_date") or raw.get("date") or raw.get("period")
        )
        if period_date is None:
            period_date = datetime.now(timezone.utc)

        return OperationalMetricRecord(
            customer_id=self.customer_id,
            metric_type=canonical_type,
            value=value,
            period_date=period_date.date(),
            facility=raw.get("facility") or raw.get("site") or raw.get("location"),
            department=raw.get("department") or raw.get("cost_center"),
            source_system=self.erp_type,
            source_record_id=record_id,
            unit=raw.get("unit") or raw.get("uom"),
            raw_data=raw,
        )

    async def _validate_credentials(self) -> bool:
        """
        Test that credentials are valid by making a minimal API call.
        Called during customer onboarding and health checks.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{YOUR_SYSTEM_API_BASE}/health",
                    headers=self._get_headers(),
                )
            return response.status_code == 200
        except Exception:
            return False

    def _get_headers(self) -> dict:
        """
        Build authentication headers for your API.

        Common patterns:
          Bearer token:  {"Authorization": f"Bearer {self._credentials.get('api_key')}"}
          API key:       {"X-API-Key": self._credentials.get("api_key")}
          Basic auth:    handled by httpx auth= parameter
        """
        return {
            "Authorization": f"Bearer {self._credentials.get('api_key', '')}",
            "Content-Type":  "application/json",
        }
