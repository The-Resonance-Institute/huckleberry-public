"""
connectors/cmms/fiix.py

Fiix CMMS connector for Huckleberry.

Fiix (by Rockwell Automation) is the most common CMMS in
mid-market glass and aluminum manufacturing. REST API with
JSON responses. Authentication via API key + application key.

API base: https://api.fiixsoftware.com/api
Auth: X-Fiix-Application-Id + X-Fiix-Application-Key headers

Key endpoints used:
  POST /api/v2/workOrder/getWorkOrdersList
    Fetches work orders with filter criteria.
    Filter: date_modified >= last_sync_at

  POST /api/v2/asset/getAssetsList
    Fetches all active assets with maintenance schedule data.

Work order type mapping (Fiix intMaintenanceType):
  1 = Corrective (unplanned)
  2 = Preventive (planned)
  3 = Emergency  (unplanned + priority)
  4 = Inspection  (planned inspection)

Work order status mapping (intStatus):
  0  = Created
  1  = In Progress
  2  = Pending Review
  10 = Complete
  20 = Cancelled

Downtime field: dtmDateCompleted - dtmDateStarted when type is corrective/emergency.
The Fiix API does not always provide a dedicated downtime_hours field.
We compute it from start/complete timestamps when available.
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
    WO_TYPE_EMERGENCY,
    WO_TYPE_INSPECTION,
)

logger = logging.getLogger(__name__)

FIIX_API_BASE     = "https://api.fiixsoftware.com/api"
FIIX_API_VERSION  = "v2"
REQUEST_TIMEOUT   = 30.0
PAGE_SIZE         = 500

# Fiix maintenance type codes
FIIX_TYPE_CORRECTIVE  = 1
FIIX_TYPE_PREVENTIVE  = 2
FIIX_TYPE_EMERGENCY   = 3
FIIX_TYPE_INSPECTION  = 4

# Fiix status codes
FIIX_STATUS_COMPLETE  = 10
FIIX_STATUS_CANCELLED = 20

# Fiix criticality to canonical mapping
FIIX_CRITICALITY_MAP = {
    1: CRITICALITY_CRITICAL,
    2: CRITICALITY_HIGH,
    3: CRITICALITY_MEDIUM,
    4: CRITICALITY_LOW,
}


class FiixConnector(BaseCMMSConnector):
    """Fiix CMMS REST API connector."""

    @property
    def cmms_type(self) -> str:
        return "fiix"

    async def _validate_credentials(self) -> bool:
        """Validate Fiix API credentials by fetching a minimal asset list."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{FIIX_API_BASE}/{FIIX_API_VERSION}/asset/getAssetsList",
                    headers=self._get_headers(),
                    json={"limit": 1, "offset": 0},
                )
            return response.status_code == 200
        except Exception:
            return False

    async def _fetch_work_orders_raw(
        self,
        last_sync_at: Optional[datetime],
        limit: int,
    ) -> list[dict]:
        """Fetch work orders from Fiix API."""
        if not self._credentials:
            logger.warning(
                f"No Fiix credentials for {self.customer_slug} — returning empty"
            )
            return []

        all_records: list[dict] = []
        offset = 0

        filter_criteria: dict = {}
        if last_sync_at:
            filter_criteria["dtmDateModified"] = {
                "operator": ">=",
                "value":    last_sync_at.isoformat(),
            }

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            while True:
                payload = {
                    "limit":  min(PAGE_SIZE, limit - len(all_records)),
                    "offset": offset,
                    "filter": filter_criteria,
                    "fields": [
                        "id", "strCode", "intMaintenanceType", "intStatus",
                        "intAssetId", "strAssetName", "strSiteName",
                        "strDepartmentName", "dtmDateCreated", "dtmDateScheduled",
                        "dtmDateStarted", "dtmDateCompleted", "dtmDateDue",
                        "fltActualLabourHours", "fltEstimatedHours",
                        "strCode_failure", "strFailureCategory", "intPriority",
                    ],
                }

                try:
                    response = await client.post(
                        f"{FIIX_API_BASE}/{FIIX_API_VERSION}/workOrder/getWorkOrdersList",
                        headers=self._get_headers(),
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"Fiix work order fetch failed: {e}")
                    break

                records = data.get("workOrders", data.get("items", []))
                if not records:
                    break

                all_records.extend(records)

                if len(records) < PAGE_SIZE or len(all_records) >= limit:
                    break

                offset += PAGE_SIZE

        return all_records

    async def _fetch_assets_raw(self) -> list[dict]:
        """Fetch all active assets from Fiix."""
        if not self._credentials:
            return []

        all_records: list[dict] = []
        offset = 0

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            while True:
                payload = {
                    "limit":  PAGE_SIZE,
                    "offset": offset,
                    "filter": {"bolIsActive": True},
                    "fields": [
                        "id", "strName", "strCode", "strAssetType",
                        "strSiteName", "strDepartmentName",
                        "intCriticalityId", "dtmInstallDate",
                        "dtmLastCompletedPM", "dtmNextScheduledPM",
                        "intPMFrequency", "bolIsActive",
                    ],
                }

                try:
                    response = await client.post(
                        f"{FIIX_API_BASE}/{FIIX_API_VERSION}/asset/getAssetsList",
                        headers=self._get_headers(),
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logger.error(f"Fiix asset fetch failed: {e}")
                    break

                records = data.get("assets", data.get("items", []))
                if not records:
                    break

                all_records.extend(records)

                if len(records) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE

        return all_records

    def _normalize_work_order(self, raw: dict) -> Optional[WorkOrderRecord]:
        """Normalize a raw Fiix work order dict to a WorkOrderRecord."""
        wo_id = str(raw.get("id") or raw.get("strCode") or "")
        if not wo_id:
            return None

        maintenance_type = raw.get("intMaintenanceType", 0)
        status_code      = raw.get("intStatus", 0)

        # Map type
        if maintenance_type == FIIX_TYPE_EMERGENCY:
            wo_type = WO_TYPE_EMERGENCY
        elif maintenance_type == FIIX_TYPE_CORRECTIVE:
            wo_type = WO_TYPE_UNPLANNED
        elif maintenance_type == FIIX_TYPE_INSPECTION:
            wo_type = WO_TYPE_INSPECTION
        else:
            wo_type = WO_TYPE_PLANNED

        # Map status
        status_map = {
            FIIX_STATUS_COMPLETE:  "complete",
            FIIX_STATUS_CANCELLED: "cancelled",
        }
        status = status_map.get(status_code, "open")
        if status_code == 1:
            status = "in_progress"

        started_at   = self._safe_datetime(raw.get("dtmDateStarted"))
        completed_at = self._safe_datetime(raw.get("dtmDateCompleted"))

        # Compute downtime from start/complete gap for corrective/emergency
        downtime_hours = None
        is_unplanned = wo_type in (WO_TYPE_UNPLANNED, WO_TYPE_EMERGENCY)
        if is_unplanned and started_at and completed_at:
            delta = completed_at - started_at
            downtime_hours = Decimal(str(round(delta.total_seconds() / 3600, 3)))

        # Due date overdue check
        due_date  = self._safe_datetime(raw.get("dtmDateDue"))
        is_overdue = (
            due_date is not None
            and status not in ("complete", "cancelled")
            and due_date < datetime.now(timezone.utc)
        )

        return WorkOrderRecord(
            customer_id=self.customer_id,
            work_order_id=wo_id,
            work_order_type=wo_type,
            asset_id=str(raw.get("intAssetId", "")),
            asset_name=raw.get("strAssetName"),
            facility=raw.get("strSiteName"),
            department=raw.get("strDepartmentName"),
            created_at=self._safe_datetime(raw.get("dtmDateCreated")),
            scheduled_at=self._safe_datetime(raw.get("dtmDateScheduled")),
            started_at=started_at,
            completed_at=completed_at,
            due_date=due_date,
            actual_hours=self._safe_decimal(raw.get("fltActualLabourHours")),
            downtime_hours=downtime_hours,
            estimated_hours=self._safe_decimal(raw.get("fltEstimatedHours")),
            status=status,
            priority=str(raw.get("intPriority", "")),
            failure_code=raw.get("strCode_failure"),
            failure_category=raw.get("strFailureCategory"),
            is_unplanned=is_unplanned,
            is_overdue=is_overdue,
            raw_data=raw,
        )

    def _normalize_asset(self, raw: dict) -> Optional[AssetRecord]:
        """Normalize a raw Fiix asset dict to an AssetRecord."""
        asset_id = str(raw.get("id") or raw.get("strCode") or "")
        if not asset_id:
            return None

        asset_name = raw.get("strName", "").strip()
        if not asset_name:
            return None

        criticality_id  = raw.get("intCriticalityId", 3)
        criticality     = FIIX_CRITICALITY_MAP.get(criticality_id, CRITICALITY_MEDIUM)

        pm_freq_days = None
        if raw.get("intPMFrequency"):
            try:
                pm_freq_days = int(raw["intPMFrequency"])
            except (ValueError, TypeError):
                pass

        return AssetRecord(
            customer_id=self.customer_id,
            asset_id=asset_id,
            asset_name=asset_name,
            asset_type=raw.get("strAssetType"),
            facility=raw.get("strSiteName"),
            department=raw.get("strDepartmentName"),
            criticality=criticality,
            install_date=self._safe_datetime(raw.get("dtmInstallDate")),
            last_pm_date=self._safe_datetime(raw.get("dtmLastCompletedPM")),
            next_pm_date=self._safe_datetime(raw.get("dtmNextScheduledPM")),
            pm_frequency_days=pm_freq_days,
            is_active=bool(raw.get("bolIsActive", True)),
            raw_data=raw,
        )

    def _get_headers(self) -> dict:
        """Build Fiix API authentication headers."""
        return {
            "Content-Type":           "application/json",
            "X-Fiix-Application-Id":  self._credentials.get("application_id", ""),
            "X-Fiix-Application-Key": self._credentials.get("application_key", ""),
        }
