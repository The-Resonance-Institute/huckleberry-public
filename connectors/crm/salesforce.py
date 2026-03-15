"""
connectors/crm/salesforce.py

Salesforce connector for Huckleberry.

Uses the Salesforce REST API with OAuth 2.0 connected app credentials.
Queries Opportunity object for commercial events.

Salesforce API:
  Base URL: https://{instance}.salesforce.com/services/data/v58.0/
  Auth:     OAuth 2.0 username-password or JWT bearer flow
  Query:    SOQL via /query?q=SELECT+...+FROM+Opportunity

SOQL query:
  SELECT Id, Name, StageName, Amount, CloseDate, LastModifiedDate,
         Owner.Email, Account.BillingState, LeadSource,
         ForecastCategoryName, IsClosed, IsWon
  FROM Opportunity
  WHERE LastModifiedDate > {last_sync_at}
  ORDER BY LastModifiedDate ASC
  LIMIT {limit}

Credentials required:
  instance_url:  Salesforce instance URL (e.g. https://company.my.salesforce.com)
  access_token:  OAuth access token (refreshed via refresh_token)
  refresh_token: OAuth refresh token
  client_id:     Connected app client ID
  client_secret: Connected app client secret
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from connectors.base import BaseConnector, ConnectorError, ConnectorHealth, ConnectorResult
from connectors.field_mapper import FieldMapper
from connectors.registry import register_connector

logger = logging.getLogger(__name__)

DEFAULT_SF_FIELD_MAPPING = {
    "occurred_at":  "LastModifiedDate",
    "rep_id":       "Owner.Email",
    "region":       "Account.BillingState",
    "deal_value":   "Amount",
    "stage_to":     "StageName",
    "product_line": "LeadSource",
    "segment":      "Account.Industry",
}

SF_OPPORTUNITY_FIELDS = (
    "Id, Name, StageName, Amount, CloseDate, LastModifiedDate, "
    "Owner.Email, Account.BillingState, Account.Industry, "
    "LeadSource, IsClosed, IsWon, ForecastCategoryName"
)


@register_connector("salesforce")
class SalesforceConnector(BaseConnector):
    """Salesforce CRM connector."""

    def __init__(self, customer_id, customer_slug, customer_vertical, credentials):
        super().__init__(customer_id, customer_slug, customer_vertical, credentials)
        self._access_token: Optional[str] = credentials.get("access_token", "")
        self._instance_url: str = credentials.get("instance_url", "")
        self._token_expiry: float = 0.0

        field_mapping = credentials.get("field_mapping", DEFAULT_SF_FIELD_MAPPING)
        self.mapper = FieldMapper(
            mapping_config=field_mapping,
            stage_mapping=credentials.get("stage_mapping", {}),
            region_mapping=credentials.get("region_mapping", {}),
            product_line_mapping=credentials.get("product_line_mapping", {}),
        )

    @property
    def connector_type(self) -> str:
        return "salesforce"

    @property
    def source_system_name(self) -> str:
        return "Salesforce"

    async def _refresh_token(self) -> None:
        """Refresh Salesforce OAuth access token."""
        token_url = "https://login.salesforce.com/services/oauth2/token"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type":    "refresh_token",
                    "client_id":     self.credentials.get("client_id", ""),
                    "client_secret": self.credentials.get("client_secret", ""),
                    "refresh_token": self.credentials.get("refresh_token", ""),
                },
            )

            if response.status_code != 200:
                raise ConnectorError(
                    f"Salesforce token refresh failed: {response.status_code}",
                    connector_type=self.connector_type,
                )

            data = response.json()
            self._access_token = data["access_token"]
            self._instance_url = data.get("instance_url", self._instance_url)

    async def _soql_query(self, soql: str) -> list[dict]:
        """Execute a SOQL query and return all records."""
        if not self._access_token:
            await self._refresh_token()

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type":  "application/json",
        }
        url = f"{self._instance_url}/services/data/v58.0/query"
        records: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {"q": soql}
            while True:
                response = await client.get(url, headers=headers, params=params)

                if response.status_code == 401:
                    await self._refresh_token()
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    response = await client.get(url, headers=headers, params=params)

                if response.status_code != 200:
                    logger.error(
                        "Salesforce SOQL query failed",
                        extra={"status": response.status_code, "soql": soql[:100]},
                    )
                    break

                data = response.json()
                records.extend(data.get("records", []))

                next_url = data.get("nextRecordsUrl")
                if not next_url:
                    break
                url = f"{self._instance_url}{next_url}"
                params = {}

        return records

    async def fetch_commercial_events(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> ConnectorResult:
        result = ConnectorResult()

        where_clause = ""
        if last_sync_at:
            ts = last_sync_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            where_clause = f"WHERE LastModifiedDate > {ts}"

        soql = (
            f"SELECT {SF_OPPORTUNITY_FIELDS} "
            f"FROM Opportunity "
            f"{where_clause} "
            f"ORDER BY LastModifiedDate ASC "
            f"LIMIT {limit}"
        )

        try:
            raw_records = await self._soql_query(soql)
        except Exception as e:
            logger.error(
                "Salesforce fetch failed",
                extra={"customer": self.customer_slug, "error": str(e)},
            )
            return result

        result.total_fetched = len(raw_records)

        for raw in raw_records:
            try:
                event_type = self._classify_event_type(raw)
                canonical, quality = self.mapper.map_commercial_event(raw, event_type)
                canonical.update(
                    self._build_commercial_event_dict(
                        source_record_id=str(raw.get("Id", "")),
                        event_type=event_type,
                        occurred_at=canonical.get(
                            "occurred_at", datetime.now(timezone.utc)
                        ),
                        **{k: v for k, v in canonical.items()
                           if k not in ("occurred_at",)},
                    )
                )
                result.records.append(canonical)
            except Exception as e:
                from connectors.base import ConnectorErrorRecord
                result.errors.append(
                    ConnectorErrorRecord(
                        source_record_id=str(raw.get("Id", "unknown")),
                        error_type=type(e).__name__,
                        error_message=str(e),
                        raw_record=raw,
                    )
                )

        logger.info(
            "Salesforce fetch complete",
            extra={
                "customer": self.customer_slug,
                "fetched":  result.total_fetched,
                "mapped":   result.success_count,
            },
        )
        return result

    async def fetch_operational_metrics(self, last_sync_at=None, limit=1000):
        return ConnectorResult()

    async def fetch_external_signals(self, last_sync_at=None):
        return ConnectorResult()

    async def health_check(self) -> ConnectorHealth:
        start = time.perf_counter()
        try:
            await self._refresh_token()
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(healthy=True, latency_ms=latency,
                                   message="Salesforce reachable")
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(healthy=False, latency_ms=latency, message=str(e))

    async def validate_credentials(self) -> bool:
        try:
            await self._refresh_token()
            return True
        except ConnectorError:
            return False

    def _classify_event_type(self, raw: dict) -> str:
        if raw.get("IsWon"):
            return "deal_won"
        if raw.get("IsClosed") and not raw.get("IsWon"):
            return "deal_lost"
        stage = str(raw.get("StageName", "")).lower()
        if "proposal" in stage or "quote" in stage:
            return "quote_issued"
        if "prospecting" in stage or "qualification" in stage:
            return "opp_opened"
        return "stage_changed"
