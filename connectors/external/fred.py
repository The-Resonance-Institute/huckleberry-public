"""
connectors/external/fred.py

FRED (Federal Reserve Economic Data) connector for Huckleberry.

Fetches macroeconomic time series from the St. Louis Fed FRED API
and normalizes them to ExternalSignal records.

Series fetched for the glass/aluminum vertical:
  MORTGAGE30US  - 30-year fixed mortgage rate (weekly)
  HOUST         - Housing starts (monthly)
  PERMIT        - Building permits (monthly)
  INDPRO        - Industrial production index (monthly)
  UNRATE        - Unemployment rate (monthly)

FRED API:
  Base URL: https://api.stlouisfed.org/fred/
  Auth:     API key as query parameter
  Format:   JSON

Credentials required:
  api_key: FRED API key (free registration at fred.stlouisfed.org)
"""

import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from connectors.base import BaseConnector, ConnectorHealth, ConnectorResult
from connectors.registry import register_connector

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred"

# Series to fetch and their directional interpretation per vertical
# True = higher value is favorable, False = higher value is adverse
SERIES_CONFIG: dict[str, dict] = {
    "MORTGAGE30US": {
        "description":  "30-Year Fixed Rate Mortgage Average",
        "frequency":    "weekly",
        "unit":         "percentage",
        "direction_map": {
            "glass_aluminum":     "adverse_if_high",
            "building_materials": "adverse_if_high",
            "hvac":               "adverse_if_high",
            "roofing":            "adverse_if_high",
            "universal":          "adverse_if_high",
        },
    },
    "HOUST": {
        "description":  "Housing Starts: Total",
        "frequency":    "monthly",
        "unit":         "units",
        "direction_map": {
            "glass_aluminum":     "favorable_if_high",
            "building_materials": "favorable_if_high",
            "hvac":               "favorable_if_high",
            "roofing":            "favorable_if_high",
            "universal":          "favorable_if_high",
        },
    },
    "PERMIT": {
        "description":  "Building Permits",
        "frequency":    "monthly",
        "unit":         "units",
        "direction_map": {
            "glass_aluminum":     "favorable_if_high",
            "building_materials": "favorable_if_high",
            "universal":          "favorable_if_high",
        },
    },
    "INDPRO": {
        "description":  "Industrial Production Index",
        "frequency":    "monthly",
        "unit":         "index",
        "direction_map": {"universal": "favorable_if_high"},
    },
    "UNRATE": {
        "description":  "Unemployment Rate",
        "frequency":    "monthly",
        "unit":         "percentage",
        "direction_map": {"universal": "adverse_if_high"},
    },
}


@register_connector("fred")
class FREDConnector(BaseConnector):
    """
    FRED macroeconomic feed connector.
    Platform-level — not customer-specific.
    customer_id and customer_slug are set to platform defaults.
    """

    @property
    def connector_type(self) -> str:
        return "fred"

    @property
    def source_system_name(self) -> str:
        return "FRED (Federal Reserve Economic Data)"

    async def fetch_commercial_events(self, last_sync_at=None, limit=1000):
        return ConnectorResult()

    async def fetch_operational_metrics(self, last_sync_at=None, limit=1000):
        return ConnectorResult()

    async def fetch_external_signals(
        self,
        last_sync_at: Optional[datetime] = None,
    ) -> ConnectorResult:
        result = ConnectorResult()
        api_key = self.credentials.get("api_key", "")

        if not api_key:
            logger.warning("FRED API key not configured")
            return result

        observation_start = None
        if last_sync_at:
            observation_start = last_sync_at.strftime("%Y-%m-%d")

        async with httpx.AsyncClient(timeout=30.0) as client:
            for series_id, config in SERIES_CONFIG.items():
                try:
                    records = await self._fetch_series(
                        client, api_key, series_id, config, observation_start
                    )
                    result.records.extend(records)
                    result.total_fetched += len(records)
                except Exception as e:
                    logger.error(
                        f"FRED series fetch failed: {series_id}",
                        extra={"error": str(e)},
                    )

        return result

    async def _fetch_series(
        self,
        client: httpx.AsyncClient,
        api_key: str,
        series_id: str,
        config: dict,
        observation_start: Optional[str],
    ) -> list[dict]:
        params = {
            "series_id":   series_id,
            "api_key":     api_key,
            "file_type":   "json",
            "sort_order":  "asc",
            "limit":       "100",
        }
        if observation_start:
            params["observation_start"] = observation_start

        response = await client.get(
            f"{FRED_BASE_URL}/series/observations",
            params=params,
        )

        if response.status_code != 200:
            logger.error(
                f"FRED API error for {series_id}",
                extra={"status": response.status_code},
            )
            return []

        data = response.json()
        observations = data.get("observations", [])
        records = []

        for obs in observations:
            raw_value = obs.get("value", ".")
            if raw_value == ".":
                continue  # FRED uses "." for missing values

            try:
                value = Decimal(raw_value)
            except Exception:
                continue

            period_date_str = obs.get("date", "")
            try:
                period_date = date.fromisoformat(period_date_str)
            except ValueError:
                continue

            # Determine directional score for this vertical
            direction_map = config.get("direction_map", {})
            vertical = self.customer_vertical or "universal"
            direction_rule = direction_map.get(
                vertical,
                direction_map.get("universal", "neutral"),
            )
            # directional_score is set to None here — the signal engine
            # computes z-scores and directional scores from the historical
            # baseline during signal computation, not at ingestion time.

            records.append({
                "feed_name":   "fred",
                "series_key":  series_id,
                "vertical":    vertical if vertical in direction_map else "universal",
                "period_date": period_date,
                "value":       value,
                "normalized_zscore":   None,
                "directional_score":   None,
                "raw_payload": obs,
            })

        return records

    async def health_check(self) -> ConnectorHealth:
        start = time.perf_counter()
        api_key = self.credentials.get("api_key", "")
        if not api_key:
            return ConnectorHealth(
                healthy=False, latency_ms=0,
                message="FRED API key not configured"
            )
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{FRED_BASE_URL}/series",
                    params={
                        "series_id": "UNRATE",
                        "api_key": api_key,
                        "file_type": "json",
                    },
                )
            latency = round((time.perf_counter() - start) * 1000, 2)
            healthy = response.status_code == 200
            return ConnectorHealth(
                healthy=healthy,
                latency_ms=latency,
                message="OK" if healthy else f"HTTP {response.status_code}",
            )
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return ConnectorHealth(healthy=False, latency_ms=latency, message=str(e))

    async def validate_credentials(self) -> bool:
        health = await self.health_check()
        return health.healthy
