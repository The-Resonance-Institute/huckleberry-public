"""
connectors/external/lme.py

London Metal Exchange (LME) commodity prices connector.

Fetches aluminum and other metal spot prices relevant to the
glass and aluminum fabrication vertical.

For glass/aluminum fabricators, rising aluminum spot prices
compress margin directly. This is one of the most important
external signals for the glass_aluminum vertical.

Data source: Quandl/Nasdaq Data Link LME dataset
  Dataset: LME/PR_AL (Aluminum spot price USD per metric ton)
  Dataset: LME/PR_CU (Copper spot price USD per metric ton)

Credentials required:
  quandl_api_key: Nasdaq Data Link API key
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

QUANDL_BASE = "https://data.nasdaq.com/api/v3/datasets"

LME_SERIES = {
    "aluminum_spot_usd_mt": {
        "dataset":   "LME/PR_AL",
        "vertical":  "glass_aluminum",
        "direction": "adverse_if_high",
        # Rising aluminum cost is adverse for fabricators
    },
    "copper_spot_usd_mt": {
        "dataset":   "LME/PR_CU",
        "vertical":  "building_materials",
        "direction": "adverse_if_high",
    },
}


@register_connector("lme")
class LMEConnector(BaseConnector):
    """LME commodity prices connector via Nasdaq Data Link."""

    @property
    def connector_type(self) -> str:
        return "lme"

    @property
    def source_system_name(self) -> str:
        return "London Metal Exchange (LME)"

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
            logger.warning("Quandl API key not configured for LME connector")
            return result

        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_key, config in LME_SERIES.items():
                try:
                    records = await self._fetch_lme_series(
                        client, api_key, series_key, config, last_sync_at
                    )
                    result.records.extend(records)
                    result.total_fetched += len(records)
                except Exception as e:
                    logger.error(
                        f"LME series fetch failed: {series_key}",
                        extra={"error": str(e)},
                    )

        return result

    async def _fetch_lme_series(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        series_key: str,
        config: dict,
        last_sync_at: Optional[datetime],
    ) -> list[dict]:
        params: dict[str, Any] = {
            "api_key":  api_key,
            "order":    "asc",
            "rows":     252,
            # ~1 year of daily data
        }
        if last_sync_at:
            params["start_date"] = last_sync_at.strftime("%Y-%m-%d")

        url = f"{QUANDL_BASE}/{config['dataset']}.json"
        response = await client.get(url, params=params)

        if response.status_code != 200:
            logger.error(
                f"LME fetch failed for {series_key}",
                extra={"status": response.status_code},
            )
            return []

        data = response.json()
        dataset = data.get("dataset", {})
        column_names = dataset.get("column_names", [])
        rows = dataset.get("data", [])

        date_idx  = column_names.index("Date")  if "Date"  in column_names else 0
        value_idx = column_names.index("Price") if "Price" in column_names else 1

        records = []
        for row in rows:
            try:
                period_date = date.fromisoformat(str(row[date_idx]))
                value = Decimal(str(row[value_idx]))

                records.append({
                    "feed_name":         "lme",
                    "series_key":        series_key,
                    "vertical":          config["vertical"],
                    "period_date":       period_date,
                    "value":             value,
                    "normalized_zscore": None,
                    "directional_score": None,
                    "raw_payload":       dict(zip(column_names, row)),
                })
            except Exception as e:
                logger.warning(f"LME row parse error for {series_key}: {e}")

        return records

    async def health_check(self) -> ConnectorHealth:
        start = time.perf_counter()
        api_key = self.credentials.get("quandl_api_key", "")
        if not api_key:
            return ConnectorHealth(healthy=False, latency_ms=0,
                                   message="Quandl API key not configured")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{QUANDL_BASE}/LME/PR_AL.json",
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
