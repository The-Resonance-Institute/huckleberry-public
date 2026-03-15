"""
connectors/cmms/base_cmms.py

Base CMMS connector for Huckleberry.

Defines the two canonical abstractions all CMMS connectors must produce:

  WorkOrderRecord:
    One record per maintenance work order. Maps directly to
    OperationalMetric rows with maintenance-specific metric types.

    Canonical metric types produced:
      unplanned_downtime_hours  — hours of unplanned downtime per event
      work_order_backlog        — count of open work orders at snapshot
      mttr_hours                — mean time to repair (per asset, per period)
      pm_compliance_rate        — PM orders completed / PM orders scheduled

  AssetRecord:
    One record per tracked asset (machine, production line, facility system).
    Stored in the asset_registry table (new in Stage 15).
    Provides identity context for interpreting downtime signals.

    Fields: asset_id, asset_name, asset_type, facility, criticality,
            install_date, last_pm_date, next_pm_date

Contract rules:
  1. fetch_work_orders() must return WorkOrderFetchResult
  2. fetch_assets() must return AssetFetchResult
  3. Both methods are read-only — never write back to CMMS
  4. Credentials loaded from Secrets Manager, never hardcoded
  5. health_check() must be callable before any fetch

All CMMS connectors inherit BaseCMMSConnector and implement
the three abstract methods: _fetch_work_orders_raw(),
_fetch_assets_raw(), and _validate_credentials().
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

# CMMS metric types written to OperationalMetric
CMMS_METRIC_TYPES = frozenset({
    "unplanned_downtime_hours",
    "work_order_backlog",
    "mttr_hours",
    "mtbf_days",
    "pm_compliance_rate",
})

# Work order type classification
WO_TYPE_PLANNED   = "planned"
WO_TYPE_UNPLANNED = "unplanned"
WO_TYPE_EMERGENCY = "emergency"
WO_TYPE_INSPECTION = "inspection"

# Asset criticality levels
CRITICALITY_CRITICAL = "critical"
CRITICALITY_HIGH     = "high"
CRITICALITY_MEDIUM   = "medium"
CRITICALITY_LOW      = "low"


@dataclass
class WorkOrderRecord:
    """
    Canonical work order record.
    One instance per maintenance work order fetched from CMMS.
    Maps to OperationalMetric rows in the database.
    """
    customer_id:      uuid.UUID
    work_order_id:    str              # Source system WO ID
    work_order_type:  str              # planned | unplanned | emergency | inspection
    asset_id:         Optional[str]
    asset_name:       Optional[str]
    facility:         Optional[str]
    department:       Optional[str]

    # Timing
    created_at:       Optional[datetime]
    scheduled_at:     Optional[datetime]
    started_at:       Optional[datetime]
    completed_at:     Optional[datetime]
    due_date:         Optional[datetime]

    # Duration and downtime
    actual_hours:     Optional[Decimal]   # Labor hours to complete
    downtime_hours:   Optional[Decimal]   # Asset downtime hours caused
    estimated_hours:  Optional[Decimal]

    # Status
    status:           str               # open | in_progress | complete | cancelled
    priority:         Optional[str]

    # Classification
    failure_code:     Optional[str]
    failure_category: Optional[str]

    # Derived metrics (computed from raw fields)
    is_unplanned:     bool = False
    is_overdue:       bool = False

    # Raw source data preserved for exploratory agent
    raw_data:         dict = field(default_factory=dict)

    def to_operational_metrics(self) -> list[dict]:
        """
        Convert this work order to OperationalMetric dicts.
        Returns one metric dict per relevant metric type.
        """
        metrics = []
        period_date = (
            self.completed_at or self.created_at
            or datetime.now(timezone.utc)
        )

        # Unplanned downtime hours
        if self.is_unplanned and self.downtime_hours is not None:
            metrics.append({
                "customer_id":   self.customer_id,
                "metric_type":   "unplanned_downtime_hours",
                "value":         self.downtime_hours,
                "period_date":   period_date.date(),
                "facility":      self.facility,
                "source_system": "cmms",
                "source_record_id": self.work_order_id,
                "unit":          "hours",
            })

        # MTTR — only for completed unplanned work orders
        if (self.is_unplanned
                and self.started_at
                and self.completed_at
                and self.actual_hours is not None):
            metrics.append({
                "customer_id":   self.customer_id,
                "metric_type":   "mttr_hours",
                "value":         self.actual_hours,
                "period_date":   period_date.date(),
                "facility":      self.facility,
                "source_system": "cmms",
                "source_record_id": self.work_order_id,
                "unit":          "hours",
            })

        return metrics


@dataclass
class AssetRecord:
    """
    Canonical asset record.
    One instance per tracked asset (machine, line, system).
    Stored in asset_registry table.
    """
    customer_id:   uuid.UUID
    asset_id:      str          # Source system asset ID
    asset_name:    str
    asset_type:    Optional[str]  # pump, conveyor, furnace, compressor, etc.
    facility:      Optional[str]
    department:    Optional[str]
    criticality:   str = CRITICALITY_MEDIUM

    # Maintenance schedule
    install_date:  Optional[datetime] = None
    last_pm_date:  Optional[datetime] = None
    next_pm_date:  Optional[datetime] = None
    pm_frequency_days: Optional[int]  = None

    # Current status
    is_active:     bool = True
    raw_data:      dict = field(default_factory=dict)


@dataclass
class WorkOrderFetchResult:
    """Result from fetch_work_orders()."""
    records:       list[WorkOrderRecord]
    success_count: int
    error_count:   int
    errors:        list[str] = field(default_factory=list)
    fetched_at:    datetime  = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def unplanned_count(self) -> int:
        return sum(1 for r in self.records if r.is_unplanned)

    @property
    def total_downtime_hours(self) -> Decimal:
        return sum(
            (r.downtime_hours for r in self.records
             if r.is_unplanned and r.downtime_hours is not None),
            Decimal("0"),
        )


@dataclass
class AssetFetchResult:
    """Result from fetch_assets()."""
    records:       list[AssetRecord]
    success_count: int
    error_count:   int
    errors:        list[str] = field(default_factory=list)

    @property
    def critical_asset_count(self) -> int:
        return sum(1 for r in self.records
                   if r.criticality == CRITICALITY_CRITICAL)


@dataclass
class CMSHealthCheck:
    """Result from health_check()."""
    healthy:     bool
    message:     str
    latency_ms:  Optional[float] = None
    checked_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseCMMSConnector(ABC):
    """
    Abstract base class for all CMMS connectors.

    Subclasses must implement:
      _fetch_work_orders_raw() -> list[dict]
      _fetch_assets_raw()      -> list[dict]
      _validate_credentials()  -> bool
      _normalize_work_order()  -> Optional[WorkOrderRecord]
      _normalize_asset()       -> Optional[AssetRecord]
    """

    def __init__(
        self,
        customer_id: uuid.UUID,
        customer_slug: str,
        customer_vertical: str,
    ) -> None:
        self.customer_id       = customer_id
        self.customer_slug     = customer_slug
        self.customer_vertical = customer_vertical
        self._credentials:     dict = {}
        self._initialized:     bool = False

    async def initialize(self) -> None:
        """Load credentials from Secrets Manager."""
        try:
            self._credentials = await self._load_credentials()
            self._initialized = True
        except Exception as e:
            logger.warning(
                f"CMMS credential load failed for {self.customer_slug}: {e}"
            )

    async def _load_credentials(self) -> dict:
        """Load CMMS credentials from Secrets Manager."""
        import json
        import boto3
        from config import get_settings
        settings = get_settings()

        if settings.is_local:
            return {}

        client = boto3.client("secretsmanager", region_name=settings.aws_region)
        secret_name = f"huckleberry-{settings.environment}/connectors/credentials"

        try:
            response = client.get_secret_value(SecretId=secret_name)
            all_creds = json.loads(response["SecretString"])
            customer_creds = all_creds.get(self.customer_slug, {})
            return customer_creds.get(self.cmms_type, {})
        except Exception:
            return {}

    async def fetch_work_orders(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> WorkOrderFetchResult:
        """
        Fetch work orders since last_sync_at.
        Returns WorkOrderFetchResult with normalized WorkOrderRecord list.
        """
        raw_records = await self._fetch_work_orders_raw(
            last_sync_at=last_sync_at,
            limit=limit,
        )

        records:       list[WorkOrderRecord] = []
        error_count:   int                   = 0
        errors:        list[str]             = []

        for raw in raw_records:
            try:
                record = self._normalize_work_order(raw)
                if record is not None:
                    records.append(record)
            except Exception as e:
                error_count += 1
                errors.append(f"WO normalization failed: {e}")
                logger.debug(f"Work order normalization error: {e}")

        return WorkOrderFetchResult(
            records=records,
            success_count=len(records),
            error_count=error_count,
            errors=errors,
        )

    async def fetch_assets(self) -> AssetFetchResult:
        """
        Fetch all active assets from the CMMS.
        Returns AssetFetchResult with normalized AssetRecord list.
        """
        raw_records = await self._fetch_assets_raw()

        records:     list[AssetRecord] = []
        error_count: int               = 0
        errors:      list[str]         = []

        for raw in raw_records:
            try:
                record = self._normalize_asset(raw)
                if record is not None:
                    records.append(record)
            except Exception as e:
                error_count += 1
                errors.append(f"Asset normalization failed: {e}")

        return AssetFetchResult(
            records=records,
            success_count=len(records),
            error_count=error_count,
            errors=errors,
        )

    async def health_check(self) -> CMSHealthCheck:
        """Test connectivity and credential validity."""
        import time
        start = time.perf_counter()
        try:
            valid = await self._validate_credentials()
            latency = round((time.perf_counter() - start) * 1000, 1)
            return CMSHealthCheck(
                healthy=valid,
                message="Connected" if valid else "Credential validation failed",
                latency_ms=latency,
            )
        except Exception as e:
            return CMSHealthCheck(
                healthy=False,
                message=f"Health check failed: {e}",
            )

    async def validate_credentials(self) -> bool:
        """Public credential validation method."""
        result = await self.health_check()
        return result.healthy

    @property
    @abstractmethod
    def cmms_type(self) -> str:
        """Return the connector type string (e.g. 'fiix')."""

    @abstractmethod
    async def _fetch_work_orders_raw(
        self,
        last_sync_at: Optional[datetime],
        limit: int,
    ) -> list[dict]:
        """Fetch raw work order dicts from the source system."""

    @abstractmethod
    async def _fetch_assets_raw(self) -> list[dict]:
        """Fetch raw asset dicts from the source system."""

    @abstractmethod
    async def _validate_credentials(self) -> bool:
        """Test credential validity against the source system."""

    @abstractmethod
    def _normalize_work_order(self, raw: dict) -> Optional[WorkOrderRecord]:
        """Normalize a raw work order dict to a WorkOrderRecord."""

    @abstractmethod
    def _normalize_asset(self, raw: dict) -> Optional[AssetRecord]:
        """Normalize a raw asset dict to an AssetRecord."""

    def _safe_decimal(self, val: Any) -> Optional[Decimal]:
        """Safely convert a value to Decimal."""
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    def _safe_datetime(self, val: Any) -> Optional[datetime]:
        """Safely parse a datetime value."""
        if val is None:
            return None
        if isinstance(val, datetime):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        try:
            from datetime import datetime as dt
            parsed = dt.fromisoformat(str(val).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None
