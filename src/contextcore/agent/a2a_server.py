"""
HTTP server implementation for A2A (Agent-to-Agent) protocol.
__all__ = ['A2AServer', 'create_a2a_server']


This module provides an HTTP server that implements A2A protocol endpoints,
including discovery (.well-known) and JSON-RPC message handling with support
for both Flask and FastAPI frameworks.
"""

from typing import Optional, Dict, Any, Union
import logging

# Import dependencies with graceful fallback handling
try:
    from flask import Flask, jsonify, request
    HAS_FLASK = True
except ImportError:
    Flask = jsonify = request = None
    HAS_FLASK = False

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    HAS_FASTAPI = True
except ImportError:
    FastAPI = HTTPException = Request = JSONResponse = None
    HAS_FASTAPI = False

from contextcore.a2a.models import AgentCard, AgentCapabilities
from contextcore.a2a.handler import A2AMessageHandler
from contextcore.a2a.discovery import DiscoveryEndpoint
from contextcore.api import HandoffsAPI, SkillsAPI

logger = logging.getLogger(__name__)


class A2AServer:
    """HTTP server implementing A2A protocol endpoints.
    
    Provides both discovery endpoints (.well-known) and JSON-RPC message
    handling with support for Flask and FastAPI frameworks.
    """

    def __init__(
        self,
        agent_card: AgentCard,
        handoffs_api: HandoffsAPI,
        skills_api: SkillsAPI,
        host: str = "0.0.0.0",
        port: int = 8080,
    ):
        """Initialize A2A server with required components."""
        self.agent_card = agent_card
        self.handler = A2AMessageHandler(handoffs_api, skills_api, agent_card)
        self.discovery = DiscoveryEndpoint(agent_card)
        self.host = host
        self.port = port
        self._app = None

    def create_flask_app(self) -> Flask:
        """Create Flask application with A2A endpoints."""
        if not HAS_FLASK:
            raise RuntimeError("Flask is not available. Install with: pip install flask")

        app = Flask(__name__)

        @app.route("/.well-known/agent.json", methods=["GET"])
        def get_agent_json():
            """Return agent card information."""
            try:
                return jsonify(self.discovery.get_a2a_agent_json())
            except Exception as e:
                logger.error(f"Error serving agent.json: {e}")
                return jsonify({"error": "Internal server error"}), 500

        @app.route("/.well-known/contextcore.json", methods=["GET"])
        def get_contextcore_json():
            """Return ContextCore-specific metadata."""
            try:
                return jsonify(self.discovery.get_contextcore_json())
            except Exception as e:
                logger.error(f"Error serving contextcore.json: {e}")
                return jsonify({"error": "Internal server error"}), 500

        @app.route("/a2a", methods=["POST"])
        def handle_a2a():
            """Handle A2A JSON-RPC messages."""
            try:
                # Validate content type
                if not request.is_json:
                    return self._json_rpc_error(-32700, "Invalid Content-Type", None)
                
                req_data = request.get_json(force=True)
                if req_data is None:
                    return self._json_rpc_error(-32700, "Parse error", None)
                
                result = self.handler.handle(req_data)
                return jsonify(result)
                
            except Exception as e:
                logger.error(f"Error handling A2A request: {e}")
                return self._json_rpc_error(-32603, "Internal error", None)

        @app.route("/health", methods=["GET"])
        def health():
            """Health check endpoint."""
            return jsonify({
                "status": "ok", 
                "agent_id": self.agent_card.agent_id,
                "framework": "flask"
            })

        self._app = app
        return app

    def create_fastapi_app(self) -> FastAPI:
        """Create FastAPI application with A2A endpoints."""
        if not HAS_FASTAPI:
            raise RuntimeError("FastAPI is not available. Install with: pip install fastapi uvicorn")

        app = FastAPI(
            title=self.agent_card.name,
            version=self.agent_card.version,
            description=f"A2A server for {self.agent_card.name}"
        )

        @app.get("/.well-known/agent.json")
        async def get_agent_json():
            """Return agent card information."""
            return self.discovery.get_a2a_agent_json()

        @app.get("/.well-known/contextcore.json")
        async def get_contextcore_json():
            """Return ContextCore-specific metadata."""
            return self.discovery.get_contextcore_json()

        @app.post("/a2a")
        async def handle_a2a(request: Request):
            """Handle A2A JSON-RPC messages."""
            try:
                req_data = await request.json()
                result = self.handler.handle(req_data)
                return JSONResponse(content=result)
            except ValueError as e:
                # JSON parsing error
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None
                }
                return JSONResponse(content=error_response, status_code=400)
            except Exception as e:
                logger.error(f"Error handling A2A request: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": "Internal error"},
                    "id": None
                }
                return JSONResponse(content=error_response, status_code=500)

        @app.get("/health")
        async def health():
            """Health check endpoint."""
            return {
                "status": "ok", 
                "agent_id": self.agent_card.agent_id,
                "framework": "fastapi"
            }

        self._app = app
        return app

    def _json_rpc_error(self, code: int, message: str, request_id: Any) -> tuple:
        """Create JSON-RPC 2.0 compliant error response for Flask."""
        error_response = {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": request_id
        }
        status_code = 400 if code == -32700 else 500
        return jsonify(error_response), status_code

    def run_flask(self, debug: bool = False, **kwargs):
        """Start Flask development server."""
        app = self.create_flask_app()
        logger.info(f"Starting Flask server on {self.host}:{self.port}")
        app.run(host=self.host, port=self.port, debug=debug, **kwargs)

    def run_uvicorn(self, reload: bool = False, **kwargs):
        """Start FastAPI server with uvicorn."""
        try:
            import uvicorn
        except ImportError:
            raise RuntimeError("uvicorn is not available. Install with: pip install uvicorn")
        
        app = self.create_fastapi_app()
        logger.info(f"Starting FastAPI server on {self.host}:{self.port}")
        uvicorn.run(app, host=self.host, port=self.port, reload=reload, **kwargs)

    def run(self, framework: str = "flask", **kwargs):
        """Start server with specified framework.
        
        Args:
            framework: Either "flask" or "fastapi"
            **kwargs: Additional arguments passed to the framework runner
        """
        framework = framework.lower()
        
        if framework == "flask":
            if not HAS_FLASK:
                if HAS_FASTAPI:
                    logger.warning("Flask not available, falling back to FastAPI")
                    framework = "fastapi"
                else:
                    raise RuntimeError("Neither Flask nor FastAPI is available")
        elif framework == "fastapi":
            if not HAS_FASTAPI:
                if HAS_FLASK:
                    logger.warning("FastAPI not available, falling back to Flask")
                    framework = "flask"
                else:
                    raise RuntimeError("Neither Flask nor FastAPI is available")
        
        if framework == "flask":
            self.run_flask(**kwargs)
        elif framework == "fastapi":
            self.run_uvicorn(**kwargs)
        else:
            raise ValueError(f"Unknown framework: {framework}. Use 'flask' or 'fastapi'")

    def get_app(self, framework: str = "flask"):
        """Get the underlying web application object."""
        if framework.lower() == "flask":
            return self.create_flask_app()
        elif framework.lower() == "fastapi":
            return self.create_fastapi_app()
        else:
            raise ValueError(f"Unknown framework: {framework}")


def create_a2a_server(
    agent_id: str,
    agent_name: str,
    base_url: str,
    project_id: str,
    host: str = "0.0.0.0",
    port: int = 8080,
    tempo_url: str = "http://localhost:3200",
) -> A2AServer:
    """Factory to create A2A server with all dependencies.
    
    Args:
        agent_id: Unique identifier for the agent
        agent_name: Human-readable name for the agent
        base_url: Base URL where the server will be accessible
        project_id: Project identifier for the handoffs API
        host: Host to bind the server to
        port: Port to bind the server to  
        tempo_url: URL of the Tempo service
        
    Returns:
        Configured A2AServer instance
    """
    # Create agent card with capabilities
    agent_card = AgentCard(
        agent_id=agent_id,
        name=agent_name,
        description=f"ContextCore agent: {agent_name}",
        url=base_url,
        version="1.0.0",
        capabilities=AgentCapabilities(),
        skills=[],  # Skills will be populated by SkillsAPI
        tempo_url=tempo_url,
    )

    # Initialize API clients
    handoffs_api = HandoffsAPI(project_id=project_id, agent_id=agent_id)
    skills_api = SkillsAPI(agent_id=agent_id)

    return A2AServer(agent_card, handoffs_api, skills_api, host, port)


__all__ = [
    "A2AServer",
    "create_a2a_server",
]
