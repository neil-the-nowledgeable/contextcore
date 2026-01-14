"""
ContextCore Demo - microservices-demo Integration.

This module provides tools for demonstrating ContextCore's value proposition
using Google's Online Boutique (microservices-demo) as the target application.

Features:
- Generate realistic historical project data as OTel spans
- Create ProjectContext CRDs for all 11 microservices
- Deploy local observability stack for visualization

Usage:
    # Generate 3-month demo project history
    contextcore demo generate --project online-boutique

    # Load generated spans into Tempo
    contextcore demo load --endpoint localhost:4317

    # Set up local kind cluster with observability stack
    contextcore demo setup
"""

__all__ = [
    "HistoricalTaskTracker",
    "generate_demo_data",
    "load_to_tempo",
    "SERVICE_CONFIGS",
]


def __getattr__(name: str):
    if name == "HistoricalTaskTracker":
        from contextcore.demo.generator import HistoricalTaskTracker
        return HistoricalTaskTracker
    if name == "generate_demo_data":
        from contextcore.demo.generator import generate_demo_data
        return generate_demo_data
    if name == "load_to_tempo":
        from contextcore.demo.exporter import load_to_tempo
        return load_to_tempo
    if name == "SERVICE_CONFIGS":
        from contextcore.demo.project_data import SERVICE_CONFIGS
        return SERVICE_CONFIGS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
