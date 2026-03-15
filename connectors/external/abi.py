"""
connectors/external/abi.py

Architecture Billings Index (ABI) connector for Huckleberry.

The ABI is published monthly by the American Institute of Architects.
It is a leading indicator of nonresidential construction activity —
architecture billings lead construction starts by 9-12 months.

For glass and aluminum fabricators, a softening ABI (below 50)
is an adverse signal 9-12 months forward. An improving ABI is
a favorable leading demand signal.

ABI data is not available via a public API. It is published as a
monthly press release on the AIA website. This connector fetches
the data from a third-party aggregator (Quandl/Nasdaq Data Link)
which provides structured historical access.

Credentials required:
  quandl_api_key: Nasdaq Data Link (formerly Quandl) API key
"""

import logging
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import httpx

from connectors.base import BaseConnector, ConnectorHealth, ConnectorResult
from connectors.registry import register_connector

logger = logging.getLogger(__name__)

QUANDL_ABI_URL = "https://data.nasdaq.com/api/v3/datasets/AIA/ABI.json"


@register_connector("abi")
class ABIConnector(BaseConnector):
    """
    Architecture Billings Index connector.
    Fetches monthly ABI data from Nasdaq Data Link.
    """

    @property
    def connector_type(self) -> str:
        return "abi"

    @property
    def source_system_name(self) -> str:
        return "Architecture Billings Index (AIA)"

    async def fetch_commercial_events(self, last_sync_at=None, limit=1000):
        return ConnectorResult()

    async def fetch_operational_metrics(self, last_sync_at=None, limit=1000):
        return ConnectorResult()

    async def fetch_external_signals(
        self,
        last_sync_at: Optional[datetime] = None,
    ) -> ConnectorResult:
        result = ConnectorResult()
        api_key = self.credentials.get("quandl_api_key", "")

        if not api_key:
            logger.warning("Quandl API key not configured for ABI connector")
            return result

        params: dict[str, Any] = {
            "api_key":  api_key,
            "order":    "asc",
            "rows":     24,
        }

        if last_sync_at:
            params["start_date"] = last_sync_at.strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(QUANDL_ABI_URL, params=params)

            if response.status_code != 200:
                logger.error(
                    "ABI fetch failed",
                    extra={"status": response.status_code},
                )
                return result

            data = response.json()
            dataset = data.get("dataset", {})
            column_names = dataset.get("column_names", [])
            rows = dataset.get("data", [])

            # Find column indices
            date_idx  = column_names.index("Date") if "Date" in column_names else 0
            abi_idx   = column_names.index("ABI") if "ABI" in column_names else 1
            inq_idx   = (
                column_names.index("Architecture Billings Index - Inquiries")
                if "Architecture Billings Index - Inquiries" in column_names
                else None
            )

            result.total_fetched = len(rows)

            for row in rows:
                try:
                    period_date = date.fromisoformat(str(row[date_idx]))
                    abi_value = Decimal(str(row[abi_idx]))

                    # ABI above 50 = billings expanding = favorable for construction
                    # ABI below 50 = billings contracting = adverse
                    directional_score = None  # Set by signal engine from z-score

                    result.records.append({
                        "feed_name":         "abi",
                        "series_key":        "abi_index",
                        "vertical":          "universal",
                        "period_date":       period_date,
                        "value":             abi_value,
                        "normalized_zscore": None,
                        "directional_score": directional_score,
                        "raw_payload":       dict(zip(column_names, row)),
                    })

                    # Also record inquiries if available
                    if inq_idx is not None and row[inq_idx] is not None:
                        result.records.append({
                            "feed_name":         "abi",
                            "series_key":        "abi_inquiries",
                            "vertical":          "universal",
                            "period_date":       period_date,
                            "value":             Decimal(str(row[inq_idx])),
                            "normalized_zscore": None,
                            "directional_score": None,
                            "raw_payload":       {"date": str(period_date), "inquiries": row[inq_idx]},
                        })

                except Exception as e:
                    logger.warning(f"ABI row parse error: {e}")

        except Exception as e:
            logger.error(f"ABI connector error: {e}")

        return result

    async def health_check(self) -> ConnectorHealth:
        start = time.perf_counter()
        api_key = self.credentials.get("quandl_api_key", "")
        if not api_key:
            return ConnectorHealth(healthy=False, latency_ms=0,
                                   message="Quandl API key not configured")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    QUANDL_ABI_URL,
                    params={"api_key": api_key, "rows": 1},
                )
            latency = round((time.perf_counter() - start) * 1000, 2)
            healthy = response.status_code == 200
            return ConnectorHealth(healthy=healthy, latency_ms=latency,
                                   message="OK" if healthy else f"HTTP {response.status_code}")
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(healthy=False, latency_ms=latency, message=str(e))

    async def validate_credentials(self) -> bool:
        health = await self.health_check()
        return health.healthy
