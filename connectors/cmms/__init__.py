"""
connectors/cmms/__init__.py

CMMS (Computerized Maintenance Management System) connector package.

Extends the Huckleberry connector framework with a third connector
category alongside CRM and ERP. CMMS connectors provide operational
reliability data that neither CRM nor ERP captures:

  Work Orders:
    Planned and unplanned maintenance events at the asset level.
    Source for: unplanned_downtime_hours, mttr_hours, work_order_backlog

  PM Compliance:
    Preventive maintenance schedule adherence by asset and facility.
    Source for: pm_compliance_rate, mtbf_days

  Asset Registry:
    Critical equipment with maintenance history and failure patterns.
    Context for interpreting downtime signals.

Two canonical record abstractions (no more, no less):
  WorkOrderRecord  — one per work order, maps to OperationalMetric
  AssetRecord      — one per tracked asset, lightweight identity store

Supported CMMS systems:
  fiix       — Fiix CMMS (Rockwell Automation). REST API. Most common
               in mid-market glass/aluminum manufacturing.
  maintainx  — MaintainX. REST API. Growing in mid-market industrial.

The customer model gains a cmms_type field.
Onboarding CLI gains --cmms-type flag.

Import pattern:
    from connectors.cmms import get_cmms_connector
    from connectors.cmms.base_cmms import BaseCMMSConnector
"""

from connectors.cmms.base_cmms import BaseCMMSConnector


async def get_cmms_connector(
    customer_id,
    customer_slug: str,
    customer_vertical: str,
    cmms_type: str,
):
    """
    Factory function returning the appropriate CMMS connector instance.

    Args:
        customer_id:       Customer UUID.
        customer_slug:     Customer slug for credential lookup.
        customer_vertical: Industry vertical.
        cmms_type:         One of: fiix, maintainx

    Returns:
        Initialized BaseCMMSConnector subclass.

    Raises:
        ValueError: Unknown cmms_type.
    """
    from connectors.cmms.fiix import FiixConnector
    from connectors.cmms.maintainx import MaintainXConnector

    connectors = {
        "fiix":      FiixConnector,
        "maintainx": MaintainXConnector,
    }

    cls = connectors.get(cmms_type)
    if cls is None:
        raise ValueError(
            f"Unknown cmms_type: {cmms_type!r}. "
            f"Supported: {sorted(connectors.keys())}"
        )

    connector = cls(
        customer_id=customer_id,
        customer_slug=customer_slug,
        customer_vertical=customer_vertical,
    )
    await connector.initialize()
    return connector


__all__ = ["BaseCMMSConnector", "get_cmms_connector"]
