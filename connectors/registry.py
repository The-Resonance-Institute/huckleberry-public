"""
connectors/registry.py

Connector registry for Huckleberry.

The registry maps a (customer_slug, connector_type) pair to a
configured connector instance. The MWAA DAGs use the registry
to get the right connector without knowing which CRM or ERP
a customer uses.

Usage:
    from connectors.registry import get_connector

    connector = await get_connector(
        customer_id=customer.id,
        customer_slug=customer.slug,
        customer_vertical=customer.vertical,
        connector_type="zoho_crm",
    )
    result = await connector.fetch_commercial_events(last_sync_at=last_sync)

Design:

  Registry is a singleton at module level.
  Connector instances are created on demand and not cached —
  credentials may rotate and each fetch should use fresh credentials
  from Secrets Manager.

  Supported connector types are registered at import time.
  Adding a new connector type requires:
    1. Create the connector class in connectors/crm/ or connectors/erp/
    2. Register it here with CONNECTOR_REGISTRY[type_string] = ConnectorClass
    3. Add tests in tests/connectors/

  Credentials are loaded from Secrets Manager on each get_connector() call.
  The credentials secret structure is:
    { customer_slug: { connector_type: { ...credentials... } } }
"""

import uuid
from typing import Any, Optional, Type

from connectors.base import BaseConnector


# Registry maps connector_type string -> connector class
# Populated at module level — import order matters
CONNECTOR_REGISTRY: dict[str, Type[BaseConnector]] = {}


def register_connector(connector_type: str):
    """
    Decorator to register a connector class.

    Usage:
        @register_connector("zoho_crm")
        class ZohoCRMConnector(BaseConnector):
            ...
    """
    def decorator(cls: Type[BaseConnector]) -> Type[BaseConnector]:
        CONNECTOR_REGISTRY[connector_type] = cls
        return cls
    return decorator


def _load_connector_classes() -> None:
    """
    Import all connector modules to trigger their @register_connector
    decorators. Called once at module initialization.
    """
    try:
        from connectors.crm import zoho       # noqa: F401
        from connectors.crm import salesforce  # noqa: F401
    except ImportError:
        pass

    try:
        from connectors.erp import dynamics_ax  # noqa: F401
    except ImportError:
        pass

    try:
        from connectors.external import fred  # noqa: F401
        from connectors.external import abi   # noqa: F401
        from connectors.external import lme   # noqa: F401
    except ImportError:
        pass


async def _load_credentials(
    customer_slug: str,
    connector_type: str,
) -> dict[str, Any]:
    """
    Load connector credentials from Secrets Manager.

    Credentials secret structure:
    {
        "trulite_glass": {
            "zoho_crm": {
                "client_id": "...",
                "client_secret": "...",
                "refresh_token": "...",
                "org_id": "..."
            },
            "dynamics_ax": {
                "tenant_id": "...",
                "client_id": "...",
                "client_secret": "...",
                "base_url": "..."
            }
        }
    }
    """
    from config import get_settings
    settings = get_settings()

    if settings.is_local:
        # In local dev, return empty credentials — connectors use mock data
        return {}

    import boto3
    import json

    client = boto3.client("secretsmanager", region_name=settings.aws_region)

    from config.secrets import _get_secret
    all_credentials = _get_secret(
        settings.app_secrets_arn or "",
        settings.aws_region,
    )

    customer_creds = all_credentials.get(customer_slug, {})
    connector_creds = customer_creds.get(connector_type, {})

    if not connector_creds:
        raise RuntimeError(
            f"No credentials found for customer={customer_slug!r} "
            f"connector_type={connector_type!r}. "
            f"Run the onboarding connector setup flow."
        )

    return connector_creds


async def get_connector(
    customer_id: uuid.UUID,
    customer_slug: str,
    customer_vertical: str,
    connector_type: str,
) -> BaseConnector:
    """
    Get a configured connector instance for a customer.

    Args:
        customer_id:       Customer UUID for multi-tenant isolation.
        customer_slug:     Customer slug for credential lookup.
        customer_vertical: Industry vertical for directional scoring.
        connector_type:    One of the registered connector type strings.

    Returns:
        Configured BaseConnector instance ready for use.

    Raises:
        ValueError:   connector_type is not registered.
        RuntimeError: Credentials not found in Secrets Manager.
    """
    _load_connector_classes()

    connector_class = CONNECTOR_REGISTRY.get(connector_type)
    if connector_class is None:
        available = sorted(CONNECTOR_REGISTRY.keys())
        raise ValueError(
            f"Unknown connector type: {connector_type!r}. "
            f"Registered types: {available}"
        )

    credentials = await _load_credentials(customer_slug, connector_type)

    return connector_class(
        customer_id=customer_id,
        customer_slug=customer_slug,
        customer_vertical=customer_vertical,
        credentials=credentials,
    )


def list_registered_connectors() -> list[str]:
    """Return sorted list of all registered connector type strings."""
    _load_connector_classes()
    return sorted(CONNECTOR_REGISTRY.keys())


class ConnectorRegistry:
    """
    Namespace class providing registry access.
    Import either the module functions or this class — both work.
    """
    get = staticmethod(get_connector)
    list_types = staticmethod(list_registered_connectors)
    register = staticmethod(register_connector)
