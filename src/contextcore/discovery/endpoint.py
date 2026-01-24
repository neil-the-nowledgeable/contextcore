"""
Well-known discovery endpoint handler for serving agent cards.

Provides framework-agnostic HTTP endpoint handlers that serve .well-known/agent.json (A2A)
and .well-known/contextcore.json (extended) discovery documents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, TYPE_CHECKING, Union

if TYPE_CHECKING:
    import flask
    import fastapi

from contextcore.agents.card import AgentCard

__all__ = [
    'DiscoveryDocument',
    'DiscoveryEndpoint',
    'create_discovery_blueprint',
    'create_discovery_router'
]


@dataclass
class DiscoveryDocument:
    """ContextCore-extended discovery document structure."""
    version: str
    protocol: str  # "contextcore"
    agent: Dict[str, Any]  # AgentCard as dict
    discovery: Dict[str, Any]  # tempo_url, traceql_prefix
    endpoints: Dict[str, str]  # API endpoint paths


class DiscoveryEndpoint:
    """Framework-agnostic discovery endpoint handler."""
    
    def __init__(
        self,
        agent_card: AgentCard,
        insights_path: str = "/api/v1/insights",
        handoffs_path: str = "/api/v1/handoffs",
        skills_path: str = "/api/v1/skills",
    ) -> None:
        """Initialize discovery endpoint with agent card and API paths."""
        self.agent_card = agent_card
        self.endpoints = {
            "insights": insights_path,
            "handoffs": handoffs_path,
            "skills": skills_path,
        }

    def get_a2a_agent_json(self) -> Dict[str, Any]:
        """Returns A2A-compatible agent.json content."""
        return self.agent_card.to_a2a_json()

    def get_contextcore_json(self) -> Dict[str, Any]:
        """Returns full ContextCore discovery document."""
        return {
            "version": "1.0",
            "protocol": "contextcore",
            "agent": self.agent_card.to_contextcore_json(),
            "discovery": {
                "tempo_url": getattr(self.agent_card, 'tempo_url', None),
                "traceql_prefix": getattr(self.agent_card, 'traceql_prefix', ''),
            },
            "endpoints": self.endpoints,
        }

    def get_well_known_paths(self) -> Dict[str, Callable[[], Dict[str, Any]]]:
        """Returns mapping of paths to handler methods."""
        return {
            "/.well-known/agent.json": self.get_a2a_agent_json,
            "/.well-known/contextcore.json": self.get_contextcore_json,
        }


def create_discovery_blueprint(endpoint: DiscoveryEndpoint) -> "flask.Blueprint":
    """Create Flask blueprint for discovery endpoints."""
    try:
        import flask
    except ImportError:
        raise ImportError("Flask is required for blueprint creation")

    blueprint = flask.Blueprint('discovery', __name__)

    @blueprint.route('/.well-known/agent.json')
    def agent_json():
        """Serve A2A agent.json with content negotiation."""
        data = endpoint.get_a2a_agent_json()
        return _handle_flask_response(data, flask.request.headers.get('Accept', ''))

    @blueprint.route('/.well-known/contextcore.json')
    def contextcore_json():
        """Serve ContextCore discovery document with content negotiation."""
        data = endpoint.get_contextcore_json()
        return _handle_flask_response(data, flask.request.headers.get('Accept', ''))

    return blueprint


def create_discovery_router(endpoint: DiscoveryEndpoint) -> "fastapi.APIRouter":
    """Create FastAPI router for discovery endpoints."""
    try:
        import fastapi
    except ImportError:
        raise ImportError("FastAPI is required for router creation")

    router = fastapi.APIRouter()

    @router.get('/.well-known/agent.json')
    async def agent_json(request: fastapi.Request):
        """Serve A2A agent.json with content negotiation."""
        data = endpoint.get_a2a_agent_json()
        return _handle_fastapi_response(data, request.headers.get('accept', ''))

    @router.get('/.well-known/contextcore.json')
    async def contextcore_json(request: fastapi.Request):
        """Serve ContextCore discovery document with content negotiation."""
        data = endpoint.get_contextcore_json()
        return _handle_fastapi_response(data, request.headers.get('accept', ''))

    return router


def _handle_flask_response(data: Dict[str, Any], accept_header: str) -> Union["flask.Response", str]:
    """Handle content negotiation for Flask responses."""
    import flask
    
    # Default to JSON or if JSON is explicitly requested
    if not accept_header or 'application/json' in accept_header:
        return flask.jsonify(data)
    
    # If HTML is requested, return formatted JSON in HTML
    if 'text/html' in accept_header:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agent Discovery</title>
            <style>
                body {{ font-family: monospace; margin: 20px; }}
                pre {{ background: #f5f5f5; padding: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Agent Discovery Document</h1>
            <pre>{json.dumps(data, indent=2)}</pre>
        </body>
        </html>
        """
        return flask.Response(html_content, mimetype='text/html')
    
    # Fallback to JSON
    return flask.jsonify(data)


def _handle_fastapi_response(data: Dict[str, Any], accept_header: str) -> Union["fastapi.Response", Dict[str, Any]]:
    """Handle content negotiation for FastAPI responses."""
    from fastapi.responses import HTMLResponse, JSONResponse
    
    # Default to JSON or if JSON is explicitly requested
    if not accept_header or 'application/json' in accept_header:
        return JSONResponse(content=data)
    
    # If HTML is requested, return formatted JSON in HTML
    if 'text/html' in accept_header:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agent Discovery</title>
            <style>
                body {{ font-family: monospace; margin: 20px; }}
                pre {{ background: #f5f5f5; padding: 20px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Agent Discovery Document</h1>
            <pre>{json.dumps(data, indent=2)}</pre>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    # Fallback to JSON
    return JSONResponse(content=data)


# Basic usage
from contextcore.agents.card import AgentCard
from contextcore.discovery.endpoint import DiscoveryEndpoint

agent = AgentCard(name="MyAgent", description="Test agent")
endpoint = DiscoveryEndpoint(agent)

# Get JSON data directly
a2a_data = endpoint.get_a2a_agent_json()
cc_data = endpoint.get_contextcore_json()

# Flask integration
from flask import Flask
app = Flask(__name__)
blueprint = create_discovery_blueprint(endpoint)
app.register_blueprint(blueprint)

# FastAPI integration
from fastapi import FastAPI
app = FastAPI()
router = create_discovery_router(endpoint)
app.include_router(router)