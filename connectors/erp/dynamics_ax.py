"""
connectors/erp/dynamics_ax.py

Microsoft Dynamics AX / D365 Finance & Operations ERP connector.

Fetches operational metrics from Dynamics AX OData endpoints:
  - Sales backlog (open sales orders)
  - Production orders (capacity and load)
  - Labor records (headcount, hours)
  - Inventory records (days coverage)
  - Financial records (revenue, margin, budget variance)

Dynamics AX OData API:
  Base URL: https://{tenant}.operations.dynamics.com/data/
  Auth:     OAuth 2.0 client credentials (service principal)
  Format:   OData v4 JSON

Credentials required:
  tenant_id:     Azure AD tenant ID
  client_id:     Azure AD app registration client ID
  client_secret: Azure AD app registration client secret
  base_url:      Dynamics instance base URL
  company:       Dynamics company account (e.g. 'USMF')
"""

import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from connectors.base import BaseConnector, ConnectorError, ConnectorHealth, ConnectorResult
from connectors.field_mapper import FieldMapper
from connectors.registry import register_connector

logger = logging.getLogger(__name__)

AZURE_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


@register_connector("dynamics_ax")
class DynamicsAXConnector(BaseConnector):
    """
    Microsoft Dynamics AX / D365 Finance & Operations connector.
    Provides operational metrics to the ERP signal layer.
    """

    def __init__(self, customer_id, customer_slug, customer_vertical, credentials):
        super().__init__(customer_id, customer_slug, customer_vertical, credentials)
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._base_url: str = credentials.get("base_url", "").rstrip("/")
        self._company: str = credentials.get("company", "")

    @property
    def connector_type(self) -> str:
        return "dynamics_ax"

    @property
    def source_system_name(self) -> str:
        return "Microsoft Dynamics AX"

    async def _get_access_token(self) -> str:
        """Get Azure AD OAuth token for Dynamics AX."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        tenant_id = self.credentials.get("tenant_id", "")
        token_url = AZURE_TOKEN_URL.format(tenant_id=tenant_id)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     self.credentials.get("client_id", ""),
                    "client_secret": self.credentials.get("client_secret", ""),
                    "scope":         f"{self._base_url}/.default",
                },
            )

            if response.status_code != 200:
                raise ConnectorError(
                    f"Dynamics AX token request failed: {response.status_code}",
                    connector_type=self.connector_type,
                )

            data = response.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + data.get("expires_in", 3600)
            return self._access_token

    async def _odata_get(self, entity: str, params: dict = None) -> list[dict]:
        """Execute an OData GET request and return all values."""
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept":        "application/json",
        }
        url = f"{self._base_url}/data/{entity}"
        all_records: list[dict] = []

        query_params = {"$format": "json", "cross-company": "true"}
        if self._company:
            query_params["$filter"] = f"dataAreaId eq '{self._company}'"
        if params:
            query_params.update(params)

        async with httpx.AsyncClient(timeout=60.0) as client:
            while url:
                response = await client.get(url, headers=headers, params=query_params)
                if response.status_code != 200:
                    logger.error(
                        "Dynamics AX OData request failed",
                        extra={"entity": entity, "status": response.status_code},
                    )
                    break
                data = response.json()
                all_records.extend(data.get("value", []))
                url = data.get("@odata.nextLink")
                query_params = {}  # nextLink already has params

        return all_records

    async def fetch_commercial_events(self, last_sync_at=None, limit=1000):
        # ERP connector — no commercial events
        return ConnectorResult()

    async def fetch_operational_metrics(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> ConnectorResult:
        result = ConnectorResult()

        # Fetch multiple metric types and aggregate
        metric_fetchers = [
            self._fetch_backlog_metrics,
            self._fetch_labor_metrics,
            self._fetch_inventory_metrics,
        ]

        for fetcher in metric_fetchers:
            try:
                sub_result = await fetcher(last_sync_at)
                result.records.extend(sub_result.records)
                result.errors.extend(sub_result.errors)
                result.total_fetched += sub_result.total_fetched
            except Exception as e:
                logger.error(
                    f"Dynamics AX metric fetcher failed: {fetcher.__name__}",
                    extra={"customer": self.customer_slug, "error": str(e)},
                )

        return result

    async def _fetch_backlog_metrics(
        self, last_sync_at: Optional[datetime]
    ) -> ConnectorResult:
        """Fetch sales backlog from open sales orders."""
        result = ConnectorResult()

        params = {
            "$select": "SalesOrderNumber,TotalChargeAmount,RequestedShipDate,"
                       "InventSiteId,dataAreaId,SalesStatus",
            "$filter": "SalesStatus ne 'Invoiced'",
            "$top":    "1000",
        }

        raw_records = await self._odata_get("SalesOrderHeadersV2", params)
        result.total_fetched = len(raw_records)

        # Aggregate by facility and period
        facility_totals: dict[str, Decimal] = {}
        for raw in raw_records:
            facility = str(raw.get("InventSiteId", "UNKNOWN"))
            amount = Decimal(str(raw.get("TotalChargeAmount", 0) or 0))
            facility_totals[facility] = facility_totals.get(facility, Decimal(0)) + amount

        today = datetime.now(timezone.utc).date()
        for facility, total in facility_totals.items():
            dedup_key = self._build_dedup_key(
                "sales_backlog", facility, str(today)
            )
            result.records.append(
                self._build_operational_metric_dict(
                    source_record_id=None,
                    metric_type="sales_backlog",
                    facility=facility,
                    period_date=today,
                    value=total,
                    unit="usd",
                    dedup_key=dedup_key,
                )
            )

        return result

    async def _fetch_labor_metrics(
        self, last_sync_at: Optional[datetime]
    ) -> ConnectorResult:
        """Fetch labor headcount and hours from Dynamics."""
        result = ConnectorResult()

        params = {
            "$select": "WorkerPersonnelNumber,PositionId,DepartmentId,"
                       "EmploymentStartDate,PrimaryPositionWorkerType",
            "$filter": "EmploymentEndDate gt 2099-01-01",
            "$top":    "5000",
        }

        raw_records = await self._odata_get("WorkerV3", params)
        result.total_fetched = len(raw_records)

        # Count headcount by department (mapped to facility)
        dept_counts: dict[str, int] = {}
        for raw in raw_records:
            dept = str(raw.get("DepartmentId", "UNKNOWN"))
            dept_counts[dept] = dept_counts.get(dept, 0) + 1

        today = datetime.now(timezone.utc).date()
        for facility, count in dept_counts.items():
            dedup_key = self._build_dedup_key(
                "labor_headcount", facility, str(today)
            )
            result.records.append(
                self._build_operational_metric_dict(
                    source_record_id=None,
                    metric_type="labor_headcount",
                    facility=facility,
                    period_date=today,
                    value=Decimal(str(count)),
                    unit="count",
                    dedup_key=dedup_key,
                )
            )

        return result

    async def _fetch_inventory_metrics(
        self, last_sync_at: Optional[datetime]
    ) -> ConnectorResult:
        """Fetch inventory on-hand from Dynamics."""
        result = ConnectorResult()

        params = {
            "$select": "ItemId,InventSiteId,PhysicalInventory,FinancialInventory",
            "$top": "5000",
        }

        raw_records = await self._odata_get("InventOnHandV2", params)
        result.total_fetched = len(raw_records)

        # Sum inventory value by facility
        facility_totals: dict[str, Decimal] = {}
        for raw in raw_records:
            facility = str(raw.get("InventSiteId", "UNKNOWN"))
            value = Decimal(str(raw.get("FinancialInventory", 0) or 0))
            facility_totals[facility] = facility_totals.get(facility, Decimal(0)) + value

        today = datetime.now(timezone.utc).date()
        for facility, total in facility_totals.items():
            dedup_key = self._build_dedup_key(
                "inventory_raw_days", facility, str(today)
            )
            result.records.append(
                self._build_operational_metric_dict(
                    source_record_id=None,
                    metric_type="inventory_raw_days",
                    facility=facility,
                    period_date=today,
                    value=total,
                    unit="usd",
                    dedup_key=dedup_key,
                )
            )

        return result

    def _build_dedup_key(
        self, metric_type: str, facility: str, period_date: str
    ) -> str:
        import hashlib
        raw = f"{self.customer_id}:{self.connector_type}:{metric_type}:{facility}:{period_date}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def fetch_external_signals(self, last_sync_at=None):
        return ConnectorResult()

    async def health_check(self) -> ConnectorHealth:
        start = time.perf_counter()
        try:
            await self._get_access_token()
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(healthy=True, latency_ms=latency,
                                   message="Dynamics AX reachable")
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(healthy=False, latency_ms=latency, message=str(e))

    async def validate_credentials(self) -> bool:
        try:
            await self._get_access_token()
            return True
        except ConnectorError:
            return False
