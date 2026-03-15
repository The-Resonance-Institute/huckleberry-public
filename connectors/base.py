"""
connectors/base.py

Abstract base connector for Huckleberry.

Every connector — CRM, ERP, or external feed — must implement this
interface. The signal engine and MWAA DAGs work exclusively against
this interface. They never call source-system-specific code directly.

The contract:

  fetch_commercial_events():
    Returns raw records from the source CRM since last_sync_at.
    The field mapper normalizes them into CommercialEvent dicts.

  fetch_operational_metrics():
    Returns raw records from the source ERP since last_sync_at.
    Only meaningful for ERP connectors — CRM connectors return [].

  fetch_external_signals():
    Returns raw data points from external feeds.
    Only meaningful for external feed connectors — CRM/ERP return [].

  health_check():
    Verifies the connector can reach its source system.
    Returns ConnectorHealth with status and latency.

  validate_credentials():
    Verifies the stored credentials are valid.
    Called during onboarding and on credential refresh.

Design decisions:

  Abstract base class not protocol:
    ABC enforces the contract at class definition time with clear
    error messages. Protocol is more flexible but the connector
    framework has a stable, well-defined interface that should
    be explicit.

  ConnectorResult not raw lists:
    Wrapping results in ConnectorResult makes error handling and
    partial success explicit. A connector can return 100 records
    and 3 errors without raising an exception that loses the 100
    good records.

  last_sync_at parameter on fetch methods:
    Connectors are responsible for returning only records since
    last_sync_at. This keeps the DAG logic simple — it just passes
    the last successful sync timestamp. The connector handles
    the source-specific query logic (WHERE modified_time > X).

  customer_id and customer_slug in constructor:
    Every connector is scoped to a single customer. This prevents
    accidental cross-customer data leakage at the connector level.
"""

import abc
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ConnectorErrorRecord:
    """
    A non-fatal error from a connector fetch operation.
    Returned alongside successful records in ConnectorResult.
    """
    source_record_id: str
    error_type: str
    error_message: str
    raw_record: Optional[dict] = None


@dataclass
class ConnectorResult:
    """
    Result from a connector fetch operation.

    records: Successfully normalized records ready for database insertion.
    errors: Records that failed normalization (non-fatal).
    total_fetched: Total records retrieved from source before normalization.
    sync_cursor: Opaque cursor for the next incremental fetch.
                 None means use last_sync_at timestamp on next call.
    """
    records: list[dict] = field(default_factory=list)
    errors: list[ConnectorErrorRecord] = field(default_factory=list)
    total_fetched: int = 0
    sync_cursor: Optional[str] = None

    @property
    def success_count(self) -> int:
        return len(self.records)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def success_rate(self) -> float:
        if self.total_fetched == 0:
            return 1.0
        return self.success_count / self.total_fetched


@dataclass
class ConnectorHealth:
    """Health check result from a connector."""
    healthy: bool
    latency_ms: float
    message: str = ""
    last_successful_sync: Optional[datetime] = None


class ConnectorError(Exception):
    """
    Fatal connector error. Raised when the connector cannot proceed.
    Non-fatal per-record errors use the ConnectorError dataclass above.
    """
    def __init__(self, message: str, connector_type: str = "", cause: Optional[Exception] = None):
        super().__init__(message)
        self.connector_type = connector_type
        self.cause = cause


class BaseConnector(abc.ABC):
    """
    Abstract base class for all Huckleberry connectors.

    Every connector must implement all abstract methods.
    The connector is scoped to a single customer — never shared across
    customer boundaries.
    """

    def __init__(
        self,
        customer_id: uuid.UUID,
        customer_slug: str,
        customer_vertical: str,
        credentials: dict[str, Any],
    ) -> None:
        """
        Args:
            customer_id:       UUID of the customer this connector serves.
            customer_slug:     Slug of the customer (for logging and S3 paths).
            customer_vertical: Industry vertical (for directional scoring).
            credentials:       Source-system credentials from Secrets Manager.
        """
        self.customer_id = customer_id
        self.customer_slug = customer_slug
        self.customer_vertical = customer_vertical
        self.credentials = credentials

    @property
    @abc.abstractmethod
    def connector_type(self) -> str:
        """
        Unique identifier for this connector type.
        Examples: 'zoho_crm', 'salesforce', 'dynamics_ax', 'fred'
        Used in source_system field on canonical records.
        """
        ...

    @property
    @abc.abstractmethod
    def source_system_name(self) -> str:
        """
        Human-readable source system name for logging and error messages.
        Examples: 'Zoho CRM', 'Salesforce', 'Microsoft Dynamics AX'
        """
        ...

    @abc.abstractmethod
    async def fetch_commercial_events(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> ConnectorResult:
        """
        Fetch commercial events from the source CRM.

        Args:
            last_sync_at: Only return records modified after this timestamp.
                          None means full historical fetch (first sync only).
            limit:        Maximum records per fetch batch.

        Returns:
            ConnectorResult with normalized CommercialEvent dicts.
            Each dict must contain all required CommercialEvent fields.
        """
        ...

    @abc.abstractmethod
    async def fetch_operational_metrics(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> ConnectorResult:
        """
        Fetch operational metrics from the source ERP.

        Args:
            last_sync_at: Only return records modified after this timestamp.
            limit:        Maximum records per fetch batch.

        Returns:
            ConnectorResult with normalized OperationalMetric dicts.
            CRM connectors must return ConnectorResult() (empty).
        """
        ...

    @abc.abstractmethod
    async def fetch_external_signals(
        self,
        last_sync_at: Optional[datetime] = None,
    ) -> ConnectorResult:
        """
        Fetch external signal data points.

        Returns:
            ConnectorResult with normalized ExternalSignal dicts.
            CRM/ERP connectors must return ConnectorResult() (empty).
        """
        ...

    @abc.abstractmethod
    async def health_check(self) -> ConnectorHealth:
        """
        Verify the connector can reach its source system.
        Should complete within 5 seconds.
        Must never raise — returns unhealthy status on any error.
        """
        ...

    @abc.abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Verify stored credentials are valid.
        Returns True if credentials work, False if expired or invalid.
        """
        ...

    def _build_commercial_event_dict(
        self,
        source_record_id: str,
        event_type: str,
        occurred_at: datetime,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Build a CommercialEvent dict with required fields.
        Subclasses call this as a convenience when building records.
        """
        return {
            "customer_id":      self.customer_id,
            "source_record_id": source_record_id,
            "source_system":    self.connector_type,
            "event_type":       event_type,
            "occurred_at":      occurred_at,
            **kwargs,
        }

    def _build_operational_metric_dict(
        self,
        source_record_id: Optional[str],
        metric_type: str,
        facility: str,
        period_date: Any,
        value: Any,
        unit: str,
        dedup_key: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Build an OperationalMetric dict with required fields.
        Subclasses call this as a convenience when building records.
        """
        return {
            "customer_id":      self.customer_id,
            "source_record_id": source_record_id,
            "source_system":    self.connector_type,
            "metric_type":      metric_type,
            "facility":         facility,
            "period_date":      period_date,
            "value":            value,
            "unit":             unit,
            "dedup_key":        dedup_key,
            **kwargs,
        }

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"type={self.connector_type!r} "
            f"customer={self.customer_slug!r}>"
        )
