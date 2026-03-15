"""
connectors/__init__.py

Connector framework for Huckleberry.

The connector layer is the only layer that knows about source systems.
Everything above it — signal engine, prediction engine, Decision Ledger —
works exclusively with canonical records.

Import pattern:
    from connectors.registry import get_connector
    from connectors.base import BaseConnector, ConnectorResult
    from connectors.field_mapper import FieldMapper
"""

from connectors.base import BaseConnector, ConnectorResult, ConnectorError, ConnectorErrorRecord
from connectors.registry import ConnectorRegistry, get_connector

__all__ = [
    "BaseConnector",
    "ConnectorResult",
    "ConnectorError",
    "ConnectorErrorRecord",
    "ConnectorRegistry",
    "get_connector",
]
