"""
Project data structure for Google microservices-demo.

Defines the 11 microservices with their metadata and generates realistic
task hierarchies for demonstration purposes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from contextcore.demo.generator import HistoricalTaskTracker


@dataclass
class ServiceConfig:
    """Configuration for a microservice in the Online Boutique."""
    name: str
    language: str
    criticality: str  # critical, high, medium, low
    business_value: str  # revenue-primary, revenue-secondary, enabler, internal
    latency_p99: str
    availability: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    risks: List[Dict[str, str]] = field(default_factory=list)


# All 11 microservices from Google's microservices-demo
SERVICE_CONFIGS: Dict[str, ServiceConfig] = {
    "frontend": ServiceConfig(
        name="frontend",
        language="Go",
        criticality="critical",
        business_value="revenue-primary",
        latency_p99="500ms",
        availability="99.95",
        description="HTTP server delivering the website interface",
        dependencies=["productcatalogservice", "currencyservice", "cartservice",
                      "recommendationservice", "shippingservice", "checkoutservice", "adservice"],
        risks=[
            {"type": "availability", "priority": "P1", "description": "Customer-facing entry point"},
            {"type": "security", "priority": "P2", "description": "Handles session cookies"},
        ],
    ),
    "checkoutservice": ServiceConfig(
        name="checkoutservice",
        language="Go",
        criticality="critical",
        business_value="revenue-primary",
        latency_p99="200ms",
        availability="99.95",
        description="Orchestrates purchase workflow",
        dependencies=["productcatalogservice", "cartservice", "currencyservice",
                      "shippingservice", "paymentservice", "emailservice"],
        risks=[
            {"type": "financial", "priority": "P1", "description": "Handles payment flow"},
            {"type": "data-integrity", "priority": "P1", "description": "Order consistency"},
        ],
    ),
    "cartservice": ServiceConfig(
        name="cartservice",
        language="C#",
        criticality="critical",
        business_value="revenue-primary",
        latency_p99="100ms",
        availability="99.95",
        description="Manages shopping cart with Redis backend",
        dependencies=[],
        risks=[
            {"type": "data-integrity", "priority": "P1", "description": "Cart data loss"},
        ],
    ),
    "productcatalogservice": ServiceConfig(
        name="productcatalogservice",
        language="Go",
        criticality="high",
        business_value="revenue-primary",
        latency_p99="150ms",
        availability="99.9",
        description="Product catalog from JSON with search",
        dependencies=[],
        risks=[
            {"type": "availability", "priority": "P2", "description": "Catalog unavailability"},
        ],
    ),
    "paymentservice": ServiceConfig(
        name="paymentservice",
        language="Node.js",
        criticality="critical",
        business_value="revenue-primary",
        latency_p99="300ms",
        availability="99.99",
        description="Processes mock credit card transactions",
        dependencies=[],
        risks=[
            {"type": "security", "priority": "P1", "description": "Handles payment data"},
            {"type": "financial", "priority": "P1", "description": "Transaction integrity"},
            {"type": "compliance", "priority": "P1", "description": "PCI DSS compliance"},
        ],
    ),
    "currencyservice": ServiceConfig(
        name="currencyservice",
        language="Node.js",
        criticality="high",
        business_value="enabler",
        latency_p99="50ms",
        availability="99.9",
        description="Currency conversion using ECB rates",
        dependencies=[],
        risks=[
            {"type": "availability", "priority": "P2", "description": "High query volume service"},
        ],
    ),
    "shippingservice": ServiceConfig(
        name="shippingservice",
        language="Go",
        criticality="high",
        business_value="revenue-secondary",
        latency_p99="100ms",
        availability="99.9",
        description="Calculates shipping estimates",
        dependencies=[],
        risks=[
            {"type": "availability", "priority": "P2", "description": "Shipping calculation"},
        ],
    ),
    "emailservice": ServiceConfig(
        name="emailservice",
        language="Python",
        criticality="medium",
        business_value="enabler",
        latency_p99="1000ms",
        availability="99.5",
        description="Sends mock order confirmation emails",
        dependencies=[],
        risks=[],
    ),
    "recommendationservice": ServiceConfig(
        name="recommendationservice",
        language="Python",
        criticality="medium",
        business_value="revenue-secondary",
        latency_p99="200ms",
        availability="99.5",
        description="Product recommendations based on cart",
        dependencies=["productcatalogservice"],
        risks=[],
    ),
    "adservice": ServiceConfig(
        name="adservice",
        language="Java",
        criticality="medium",
        business_value="revenue-secondary",
        latency_p99="300ms",
        availability="99.5",
        description="Contextual text advertisements",
        dependencies=[],
        risks=[],
    ),
    "loadgenerator": ServiceConfig(
        name="loadgenerator",
        language="Python",
        criticality="low",
        business_value="internal",
        latency_p99="-",
        availability="-",
        description="Simulates user shopping behavior",
        dependencies=["frontend"],
        risks=[],
    ),
}


# Task templates for each service type
TASK_TEMPLATES = {
    "design": [
        ("Design {service} API contract", "spike", 2),
        ("Create {service} architecture diagram", "task", 1),
        ("Write ADR for {service}", "task", 1),
    ],
    "implementation": [
        ("Implement {service} gRPC server", "story", 5),
        ("Add {service} health check endpoint", "task", 2),
        ("Implement {service} core logic", "story", 8),
        ("Add {service} configuration management", "task", 2),
        ("Implement {service} error handling", "task", 3),
    ],
    "testing": [
        ("Write {service} unit tests", "task", 3),
        ("Add {service} integration tests", "task", 3),
        ("Performance test {service}", "task", 2),
    ],
    "deployment": [
        ("Create {service} Dockerfile", "task", 1),
        ("Write {service} K8s manifests", "task", 2),
        ("Add {service} to CI/CD pipeline", "task", 2),
    ],
    "observability": [
        ("Add {service} metrics endpoint", "task", 2),
        ("Instrument {service} with tracing", "task", 2),
        ("Create {service} Grafana dashboard", "task", 1),
    ],
}

# Realistic blocker scenarios
BLOCKER_SCENARIOS = [
    {
        "reason": "Waiting on API design review",
        "duration_days": (1, 3),
        "probability": 0.15,
    },
    {
        "reason": "Blocked by upstream service changes",
        "duration_days": (2, 5),
        "probability": 0.10,
    },
    {
        "reason": "Infrastructure setup pending",
        "duration_days": (1, 4),
        "probability": 0.08,
    },
    {
        "reason": "Waiting on security review",
        "duration_days": (2, 7),
        "probability": 0.05,
    },
    {
        "reason": "Third-party dependency issue",
        "duration_days": (1, 3),
        "probability": 0.07,
    },
]

# Assignee pool
ASSIGNEES = ["alice", "bob", "carol", "david", "eve", "frank"]


def generate_project_structure(
    tracker: "HistoricalTaskTracker",
    duration_months: int = 3,
    start_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Generate a complete project structure for the microservices-demo.

    Args:
        tracker: HistoricalTaskTracker instance
        duration_months: Duration in months
        start_date: Project start date (defaults to now - duration)

    Returns:
        Statistics about generated data
    """
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=duration_months * 30)

    stats = {
        "epics": 0,
        "stories": 0,
        "tasks": 0,
        "bugs": 0,
        "blockers": 0,
        "sprints": 0,
        "services": len(SERVICE_CONFIGS),
    }

    # Generate sprints (2-week sprints)
    num_sprints = (duration_months * 30) // 14
    sprints = _generate_sprints(tracker, start_date, num_sprints)
    stats["sprints"] = len(sprints)

    # Create main epic
    epic_id = "EPIC-001"
    epic_start = start_date
    epic_end = start_date + timedelta(days=duration_months * 30)

    tracker.start_task_at(
        task_id=epic_id,
        title="Online Boutique Platform Development",
        start_time=epic_start,
        task_type="epic",
        status="in_progress",
        priority="high",
    )
    stats["epics"] += 1

    # Generate tasks for each service
    task_counter = 1
    current_date = start_date

    for service_name, config in SERVICE_CONFIGS.items():
        # Create service story
        story_id = f"STORY-{service_name.upper()[:4]}-001"
        story_start = current_date
        story_duration = timedelta(days=random.randint(7, 21))

        tracker.start_task_at(
            task_id=story_id,
            title=f"Implement {service_name}",
            start_time=story_start,
            task_type="story",
            status="in_progress",
            priority="high" if config.criticality in ["critical", "high"] else "medium",
            parent_id=epic_id,
            sprint_id=_get_sprint_for_date(sprints, story_start),
            story_points=random.choice([5, 8, 13]),
        )
        stats["stories"] += 1

        # Generate tasks for this service
        task_date = story_start

        for phase, templates in TASK_TEMPLATES.items():
            for title_template, task_type, base_points in templates:
                task_id = f"TASK-{task_counter:04d}"
                task_counter += 1

                title = title_template.format(service=service_name)
                points = base_points + random.randint(-1, 1)
                points = max(1, points)

                task_start = task_date
                task_duration = timedelta(days=random.randint(1, 3))
                task_end = task_start + task_duration

                assignee = random.choice(ASSIGNEES)

                # Start task
                tracker.start_task_at(
                    task_id=task_id,
                    title=title,
                    start_time=task_start,
                    task_type=task_type if task_type != "story" else "task",
                    status="todo",
                    priority=random.choice(["high", "medium", "low"]),
                    assignee=assignee,
                    story_points=points,
                    parent_id=story_id,
                    sprint_id=_get_sprint_for_date(sprints, task_start),
                )

                # Simulate status transitions
                in_progress_time = task_start + timedelta(hours=random.randint(1, 8))
                tracker.update_status_at(task_id, "in_progress", in_progress_time)

                # Maybe add a blocker
                if _should_add_blocker():
                    blocker = random.choice(BLOCKER_SCENARIOS)
                    block_time = in_progress_time + timedelta(hours=random.randint(2, 16))
                    unblock_time = block_time + timedelta(
                        days=random.randint(*blocker["duration_days"])
                    )

                    tracker.block_task_at(task_id, blocker["reason"], block_time)
                    tracker.unblock_task_at(task_id, unblock_time)
                    task_end = unblock_time + timedelta(hours=random.randint(2, 8))
                    stats["blockers"] += 1

                # Complete task
                tracker.complete_task_at(task_id, task_end)

                if task_type == "task":
                    stats["tasks"] += 1
                elif task_type == "story":
                    stats["stories"] += 1

                task_date = task_end + timedelta(hours=random.randint(1, 4))

        # Complete the story
        story_end = task_date + timedelta(hours=random.randint(1, 4))
        tracker.complete_task_at(story_id, story_end)

        # Move to next service with some overlap
        current_date += timedelta(days=random.randint(3, 7))

    # Complete the epic
    tracker.complete_task_at(epic_id, epic_end)

    return stats


def _generate_sprints(
    tracker: "HistoricalTaskTracker",
    start_date: datetime,
    num_sprints: int,
) -> List[Dict[str, Any]]:
    """Generate sprint spans."""
    sprints = []
    sprint_start = start_date

    for i in range(num_sprints):
        sprint_id = f"sprint-{i + 1}"
        sprint_end = sprint_start + timedelta(days=14)
        planned_points = random.randint(20, 40)

        tracker.start_task_at(
            task_id=sprint_id,
            title=f"Sprint {i + 1}",
            start_time=sprint_start,
            task_type="epic",  # Sprints are parent spans
            status="in_progress",
            story_points=planned_points,
            sprint_goal=f"Sprint {i + 1} goals",
        )

        sprints.append({
            "id": sprint_id,
            "start": sprint_start,
            "end": sprint_end,
            "planned_points": planned_points,
        })

        # Complete sprint
        completed_points = int(planned_points * random.uniform(0.8, 1.1))
        tracker.complete_task_at(sprint_id, sprint_end)

        sprint_start = sprint_end

    return sprints


def _get_sprint_for_date(sprints: List[Dict], date: datetime) -> Optional[str]:
    """Get sprint ID for a given date."""
    for sprint in sprints:
        if sprint["start"] <= date < sprint["end"]:
            return sprint["id"]
    return sprints[-1]["id"] if sprints else None


def _should_add_blocker() -> bool:
    """Determine if a blocker should be added (roughly 15% of tasks)."""
    return random.random() < 0.15
