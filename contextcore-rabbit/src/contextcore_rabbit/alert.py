"""
Unified Alert model for Rabbit.

Provides a common interface for alerts from different sources
(Grafana, Alertmanager, custom webhooks).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(Enum):
    """Alert status."""
    FIRING = "firing"
    RESOLVED = "resolved"
    PENDING = "pending"


@dataclass
class Alert:
    """
    Unified alert model.

    This provides a common interface regardless of the alert source.
    """
    id: str
    name: str
    severity: AlertSeverity = AlertSeverity.MEDIUM
    status: AlertStatus = AlertStatus.FIRING
    source: str = "unknown"
    message: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    generator_url: Optional[str] = None
    fingerprint: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity.value,
            "status": self.status.value,
            "source": self.source,
            "message": self.message,
            "labels": self.labels,
            "annotations": self.annotations,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "generator_url": self.generator_url,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_grafana(cls, payload: Dict[str, Any]) -> "Alert":
        """Parse Grafana alert webhook payload."""
        import uuid

        alerts = payload.get("alerts", [payload])
        if alerts:
            alert_data = alerts[0]
        else:
            alert_data = payload

        labels = alert_data.get("labels", {})
        annotations = alert_data.get("annotations", {})

        # Map Grafana severity
        severity_map = {
            "critical": AlertSeverity.CRITICAL,
            "high": AlertSeverity.HIGH,
            "warning": AlertSeverity.MEDIUM,
            "info": AlertSeverity.INFO,
        }
        severity_str = labels.get("severity", "medium").lower()
        severity = severity_map.get(severity_str, AlertSeverity.MEDIUM)

        # Map status
        status_str = alert_data.get("status", "firing").lower()
        status = AlertStatus.RESOLVED if status_str == "resolved" else AlertStatus.FIRING

        return cls(
            id=alert_data.get("fingerprint", str(uuid.uuid4())[:8]),
            name=labels.get("alertname", payload.get("title", "Unknown Alert")),
            severity=severity,
            status=status,
            source="grafana",
            message=annotations.get("description", annotations.get("summary", "")),
            labels=labels,
            annotations=annotations,
            starts_at=alert_data.get("startsAt"),
            ends_at=alert_data.get("endsAt"),
            generator_url=alert_data.get("generatorURL"),
            fingerprint=alert_data.get("fingerprint"),
            raw_payload=payload,
        )

    @classmethod
    def from_alertmanager(cls, payload: Dict[str, Any]) -> "Alert":
        """Parse Alertmanager webhook payload."""
        import uuid

        alerts = payload.get("alerts", [])
        if alerts:
            alert_data = alerts[0]
        else:
            alert_data = payload

        labels = alert_data.get("labels", {})
        annotations = alert_data.get("annotations", {})

        severity_str = labels.get("severity", "warning").lower()
        severity_map = {
            "critical": AlertSeverity.CRITICAL,
            "warning": AlertSeverity.MEDIUM,
            "info": AlertSeverity.INFO,
        }
        severity = severity_map.get(severity_str, AlertSeverity.MEDIUM)

        status_str = alert_data.get("status", "firing").lower()
        status = AlertStatus.RESOLVED if status_str == "resolved" else AlertStatus.FIRING

        return cls(
            id=alert_data.get("fingerprint", str(uuid.uuid4())[:8]),
            name=labels.get("alertname", "Unknown Alert"),
            severity=severity,
            status=status,
            source="alertmanager",
            message=annotations.get("description", annotations.get("summary", "")),
            labels=labels,
            annotations=annotations,
            starts_at=alert_data.get("startsAt"),
            ends_at=alert_data.get("endsAt"),
            generator_url=alert_data.get("generatorURL"),
            fingerprint=alert_data.get("fingerprint"),
            raw_payload=payload,
        )

    @classmethod
    def from_manual_trigger(cls, payload: Dict[str, Any]) -> "Alert":
        """Create alert from manual trigger (e.g., Grafana panel button)."""
        import uuid

        return cls(
            id=payload.get("trigger_id", str(uuid.uuid4())[:8]),
            name=payload.get("action_name", "manual_trigger"),
            severity=AlertSeverity.INFO,
            status=AlertStatus.FIRING,
            source="manual",
            message=payload.get("message", "Manual trigger from dashboard"),
            labels=payload.get("labels", {}),
            annotations=payload.get("context", {}),
            raw_payload=payload,
        )
