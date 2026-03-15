"""
connectors/cmms/maintainx.py

MaintainX CMMS connector for Huckleberry.

MaintainX is a growing CMMS platform in mid-market industrial
manufacturing. REST API with Bearer token authentication.

API base: https://api.getmaintainx.com/v1
Auth: Authorization: Bearer {api_key}

Key endpoints used:
  GET /v1/workorders
    Fetches work orders with optional date filters.
    Query params: updatedAt[gte]={iso_datetime}&limit={n}&page={n}

  GET /v1/assets
    Fetches all assets.

Work order type mapping (MaintainX workOrderType):
  REACTIVE   = unplanned corrective
  PREVENTIVE = planned preventive
  OTHER      = planned other

Work order status mapping:
  OPEN        = open
  IN_PROGRESS = in_progress
  ON_HOLD     = open (paused)
  DONE        = complete
  CANCELLED   = cancelled

MaintainX provides a dedicated `downtimeDuration` field in seconds
on work orders, which is more reliable than computing from timestamps.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from connectors.cmms.base_cmms import (
    BaseCMMSConnector,
    WorkOrderRecord,
    AssetRecord,
    CRITICALITY_CRITICAL,
    CRITICALITY_HIGH,
    CRITICALITY_MEDIUM,
    CRITICALITY_LOW,
    WO_TYPE_PLANNED,
    WO_TYPE_UNPLANNED,
    WO_TYPE_INSPECTION,
)

logger = logging.getLogger(__name__)

MAINTAINX_API_BASE = "https://api.getmaintainx.com/v1"
REQUEST_TIMEOUT    = 30.0
PAGE_SIZE          = 100  # MaintainX max page size

# MaintainX work order types
MX_TYPE_REACTIVE   = "REACTIVE"
MX_TYPE_PREVENTIVE = "PREVENTIVE"

# MaintainX statuses
MX_STATUS_DONE      = "DONE"
MX_STATUS_CANCELLED = "CANCELLED"
MX_STATUS_IN_PROG   = "IN_PROGRESS"

# MaintainX priority to criticality mapping
MX_PRIORITY_MAP = {
    "NONE":   CRITICALITY_LOW,
    "LOW":    CRITICALITY_LOW,
    "MEDIUM": CRITICALITY_MEDIUM,
    "HIGH":   CRITICALITY_HIGH,
    "URGENT": CRITICALITY_CRITICAL,
}


class MaintainXConnector(BaseCMMSConnector):
    """MaintainX CMMS REST API connector."""

    @property
    def cmms_type(self) -> str:
        return "maintainx"

    async def _validate_credentials(self) -> bool:
        """Validate MaintainX API key."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{MAINTAINX_API_BASE}/workorders",
                    headers=self._get_headers(),
                    params={"limit": 1},
                )
            return response.status_code == 200
        except Exception:
            return False

    async def _fetch_work_orders_raw(
        self,
        last_sync_at: Optional[datetime],
        limit: int,
    ) -> list[dict]:
        """Fetch work orders from MaintainX."""
        if not self._credentials:
            logger.warning(
                f"No MaintainX credentials for {self.customer_slug}"
            )
            return []

        all_records: list[dict] = []
        page = 1

        params: dict = {"limit": PAGE_SIZE}
        if last_sync_at:
            params["updatedAt[gte]"] = last_sync_at.isoformat()

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            while True:
                params["page"] = page

                try:
                    response = await client.get(
                        f"{MAINTAINX_API_BASE}/workorders",
                        headers=self._get_headers(),
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"MaintainX work order fetch failed: {e}")
                    break

                records = data.get("workOrders", data.get("items", []))
                if not records:
                    break

                all_records.extend(records)

                if (len(records) < PAGE_SIZE
                        or len(all_records) >= limit
                        or not data.get("hasMore", False)):
                    break

                page += 1

        return all_records

    async def _fetch_assets_raw(self) -> list[dict]:
        """Fetch all assets from MaintainX."""
        if not self._credentials:
            return []

        all_records: list[dict] = []
        page = 1

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            while True:
                try:
                    response = await client.get(
                        f"{MAINTAINX_API_BASE}/assets",
                        headers=self._get_headers(),
                        params={"limit": PAGE_SIZE, "page": page},
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"MaintainX asset fetch failed: {e}")
                    break

                records = data.get("assets", data.get("items", []))
                if not records:
                    break

                all_records.extend(records)

                if len(records) < PAGE_SIZE or not data.get("hasMore", False):
                    break

                page += 1

        return all_records

    def _normalize_work_order(self, raw: dict) -> Optional[WorkOrderRecord]:
        """Normalize a raw MaintainX work order to a WorkOrderRecord."""
        wo_id = str(raw.get("id") or "")
        if not wo_id:
            return None

        mx_type  = raw.get("workOrderType", "")
        mx_status = raw.get("status", "")

        # Map type
        if mx_type == MX_TYPE_REACTIVE:
            wo_type = WO_TYPE_UNPLANNED
        elif mx_type == MX_TYPE_PREVENTIVE:
            wo_type = WO_TYPE_PLANNED
        else:
            wo_type = WO_TYPE_PLANNED

        # Map status
        if mx_status == MX_STATUS_DONE:
            status = "complete"
        elif mx_status == MX_STATUS_CANCELLED:
            status = "cancelled"
        elif mx_status == MX_STATUS_IN_PROG:
            status = "in_progress"
        else:
            status = "open"

        # MaintainX provides downtimeDuration in seconds
        downtime_hours = None
        is_unplanned   = wo_type == WO_TYPE_UNPLANNED
        if is_unplanned and raw.get("downtimeDuration"):
            try:
                seconds = float(raw["downtimeDuration"])
                downtime_hours = Decimal(str(round(seconds / 3600, 3)))
            except (ValueError, TypeError):
                pass

        started_at   = self._safe_datetime(raw.get("completionStartedAt"))
        completed_at = self._safe_datetime(raw.get("completedAt"))
        due_date     = self._safe_datetime(raw.get("dueDate"))

        is_overdue = (
            due_date is not None
            and status not in ("complete", "cancelled")
            and due_date < datetime.now(timezone.utc)
        )

        # Extract asset info from nested object if present
        asset = raw.get("asset") or {}
        asset_id   = str(asset.get("id") or raw.get("assetId") or "")
        asset_name = asset.get("name") or raw.get("assetName")

        # Location
        location = raw.get("location") or {}
        facility = location.get("name") or raw.get("locationName")

        return WorkOrderRecord(
            customer_id=self.customer_id,
            work_order_id=wo_id,
            work_order_type=wo_type,
            asset_id=asset_id or None,
            asset_name=asset_name,
            facility=facility,
            department=None,
            created_at=self._safe_datetime(raw.get("createdAt")),
            scheduled_at=self._safe_datetime(raw.get("scheduledStartDate")),
            started_at=started_at,
            completed_at=completed_at,
            due_date=due_date,
            actual_hours=self._safe_decimal(raw.get("totalActualTime")),
            downtime_hours=downtime_hours,
            estimated_hours=self._safe_decimal(raw.get("estimatedDuration")),
            status=status,
            priority=raw.get("priority"),
            failure_code=None,
            failure_category=raw.get("categories", [None])[0] if raw.get("categories") else None,
            is_unplanned=is_unplanned,
            is_overdue=is_overdue,
            raw_data=raw,
        )

    def _normalize_asset(self, raw: dict) -> Optional[AssetRecord]:
        """Normalize a raw MaintainX asset dict to an AssetRecord."""
        asset_id = str(raw.get("id") or "")
        if not asset_id:
            return None

        asset_name = (raw.get("name") or "").strip()
        if not asset_name:
            return None

        location = raw.get("location") or {}
        facility = location.get("name") or raw.get("locationName")

        return AssetRecord(
            customer_id=self.customer_id,
            asset_id=asset_id,
            asset_name=asset_name,
            asset_type=raw.get("category"),
            facility=facility,
            department=None,
            criticality=CRITICALITY_MEDIUM,
            install_date=self._safe_datetime(raw.get("purchaseDate")),
            last_pm_date=None,
            next_pm_date=None,
            pm_frequency_days=None,
            is_active=raw.get("status", "ACTIVE") == "ACTIVE",
            raw_data=raw,
        )

    def _get_headers(self) -> dict:
        """Build MaintainX API authorization headers."""
        return {
            "Authorization": f"Bearer {self._credentials.get('api_key', '')}",
            "Content-Type":  "application/json",
        }
