"""
connectors/crm/zoho.py

Zoho CRM connector for Huckleberry.

Fetches deals, contacts, and activity records from Zoho CRM and
normalizes them to CommercialEvent canonical records.

Zoho API:
  Base URL: https://www.zohoapis.com/crm/v3/
  Auth:     OAuth 2.0 with refresh token flow
  Deals:    GET /Deals?modified_time__gt={last_sync}
  Activities: GET /Activities?modified_time__gt={last_sync}

Field mapping defaults (overridden by customer config):
  Canonical field -> Zoho field
  occurred_at   -> Modified_Time
  rep_id        -> Owner.email
  region        -> Account_Name.Billing_State
  deal_value    -> Amount
  stage_from    -> (computed from stage transition history)
  stage_to      -> Stage
  product_line  -> Product_Details[0].product.name
"""

import hashlib
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

# Default Zoho -> canonical field mapping
DEFAULT_ZOHO_FIELD_MAPPING = {
    "occurred_at":  "Modified_Time",
    "rep_id":       "Owner.email",
    "region":       "Account_Name.Billing_State",
    "deal_value":   "Amount",
    "stage_to":     "Stage",
    "loss_reason":  "Reason_For_Loss__s",
    "product_line": "Product_Details.0.product.name",
    "segment":      "Account_Name.Industry",
}

ZOHO_TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
ZOHO_API_BASE  = "https://www.zohoapis.com/crm/v3"


@register_connector("zoho_crm")
class ZohoCRMConnector(BaseConnector):
    """
    Zoho CRM connector.

    Credentials required:
      client_id:     Zoho OAuth client ID
      client_secret: Zoho OAuth client secret
      refresh_token: Zoho OAuth refresh token (long-lived)
      org_id:        Zoho organization ID (optional)
    """

    def __init__(self, customer_id, customer_slug, customer_vertical, credentials):
        super().__init__(customer_id, customer_slug, customer_vertical, credentials)
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        # Build field mapper from customer config or defaults
        field_mapping = credentials.get("field_mapping", DEFAULT_ZOHO_FIELD_MAPPING)
        self.mapper = FieldMapper(
            mapping_config=field_mapping,
            stage_mapping=credentials.get("stage_mapping", {}),
            region_mapping=credentials.get("region_mapping", {}),
            product_line_mapping=credentials.get("product_line_mapping", {}),
        )

    @property
    def connector_type(self) -> str:
        return "zoho_crm"

    @property
    def source_system_name(self) -> str:
        return "Zoho CRM"

    async def _get_access_token(self) -> str:
        """Refresh OAuth access token if expired."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                ZOHO_TOKEN_URL,
                params={
                    "grant_type":    "refresh_token",
                    "client_id":     self.credentials.get("client_id", ""),
                    "client_secret": self.credentials.get("client_secret", ""),
                    "refresh_token": self.credentials.get("refresh_token", ""),
                },
            )

            if response.status_code != 200:
                raise ConnectorError(
                    f"Zoho token refresh failed: {response.status_code} {response.text}",
                    connector_type=self.connector_type,
                )

            data = response.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + data.get("expires_in", 3600)
            return self._access_token

    async def fetch_commercial_events(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> ConnectorResult:
        result = ConnectorResult()

        try:
            token = await self._get_access_token()
        except ConnectorError as e:
            logger.error(
                "Zoho token refresh failed",
                extra={"customer": self.customer_slug, "error": str(e)},
            )
            return result

        headers = {"Authorization": f"Zoho-oauthtoken {token}"}
        params: dict[str, Any] = {
            "fields": ",".join(DEFAULT_ZOHO_FIELD_MAPPING.values()),
            "per_page": min(limit, 200),
            "sort_by": "Modified_Time",
            "sort_order": "asc",
        }

        if last_sync_at:
            params["modified_time__gt"] = last_sync_at.strftime(
                "%Y-%m-%dT%H:%M:%S%z"
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{ZOHO_API_BASE}/Deals",
                headers=headers,
                params=params,
            )

            if response.status_code == 204:
                # No content — no records since last sync
                return result

            if response.status_code != 200:
                logger.error(
                    "Zoho Deals fetch failed",
                    extra={
                        "customer": self.customer_slug,
                        "status":   response.status_code,
                    },
                )
                return result

            data = response.json()
            raw_records = data.get("data", [])
            result.total_fetched = len(raw_records)

            for raw in raw_records:
                try:
                    event_type = self._classify_event_type(raw)
                    canonical, quality = self.mapper.map_commercial_event(
                        raw, event_type
                    )
                    canonical.update(
                        self._build_commercial_event_dict(
                            source_record_id=str(raw.get("id", "")),
                            event_type=event_type,
                            occurred_at=canonical.get(
                                "occurred_at",
                                datetime.now(timezone.utc),
                            ),
                            **{
                                k: v for k, v in canonical.items()
                                if k not in ("occurred_at",)
                            },
                        )
                    )
                    result.records.append(canonical)
                except Exception as e:
                    from connectors.base import ConnectorErrorRecord
                    result.errors.append(
                        ConnectorErrorRecord(
                            source_record_id=str(raw.get("id", "unknown")),
                            error_type=type(e).__name__,
                            error_message=str(e),
                            raw_record=raw,
                        )
                    )

        logger.info(
            "Zoho CRM fetch complete",
            extra={
                "customer":  self.customer_slug,
                "fetched":   result.total_fetched,
                "mapped":    result.success_count,
                "errors":    result.error_count,
            },
        )

        return result

    async def fetch_operational_metrics(
        self,
        last_sync_at: Optional[datetime] = None,
        limit: int = 1000,
    ) -> ConnectorResult:
        # CRM connector — no operational metrics
        return ConnectorResult()

    async def fetch_external_signals(
        self,
        last_sync_at: Optional[datetime] = None,
    ) -> ConnectorResult:
        # CRM connector — no external signals
        return ConnectorResult()

    async def health_check(self) -> ConnectorHealth:
        start = time.perf_counter()
        try:
            await self._get_access_token()
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(
                healthy=True,
                latency_ms=latency,
                message="Zoho CRM reachable",
            )
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(
                healthy=False,
                latency_ms=latency,
                message=str(e),
            )

    async def validate_credentials(self) -> bool:
        try:
            await self._get_access_token()
            return True
        except ConnectorError:
            return False

    def _classify_event_type(self, raw: dict[str, Any]) -> str:
        """
        Classify a Zoho Deal record into a canonical event type.
        Uses stage and closing probability to determine event type.
        """
        stage = str(raw.get("Stage", "")).lower()
        closing_date = raw.get("Closing_Date")

        if "closed won" in stage or "won" in stage:
            return "deal_won"
        if "closed lost" in stage or "lost" in stage:
            return "deal_lost"
        if "proposal" in stage or "quote" in stage:
            return "quote_issued"
        if "qualification" in stage or "needs" in stage:
            return "opp_opened"
        if raw.get("Stage_History"):
            return "stage_changed"
        return "contact_touched"
