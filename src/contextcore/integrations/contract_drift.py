"""
OpenAPI specification parser for contract drift detection.
Supports both JSON and YAML formats from URLs or local file paths.
"""
__all__ = ['EndpointSpec', 'parse_openapi']


from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.parse
import json
import yaml
import os

__all__ = ['EndpointSpec', 'parse_openapi']

@dataclass
class EndpointSpec:
    """Represents a parsed OpenAPI endpoint specification."""
    path: str
    method: str
    operation_id: Optional[str]
    request_content_type: Optional[str]
    response_content_type: Optional[str]
    response_schema: Optional[Dict[str, Any]]
    parameters: List[Dict[str, Any]]

def parse_openapi(spec_url_or_path: str) -> List[EndpointSpec]:
    """
    Parse OpenAPI specification from URL or file path.
    
    Args:
        spec_url_or_path: URL (http/https) or local file path to OpenAPI spec
        
    Returns:
        List of parsed endpoint specifications
        
    Raises:
        Exception: If spec cannot be loaded or parsed
    """
    try:
        spec = _load_spec(spec_url_or_path)
        
        endpoints = []
        paths = spec.get("paths", {})
        
        for path, methods in paths.items():
            # Skip non-method keys like parameters, summary, etc.
            http_methods = {'get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'trace'}
            
            for method, operation in methods.items():
                if method.lower() not in http_methods:
                    continue
                    
                endpoint = EndpointSpec(
                    path=path,
                    method=method.upper(),
                    operation_id=operation.get("operationId"),
                    request_content_type=_get_request_content_type(operation),
                    response_content_type=_get_response_content_type(operation),
                    response_schema=_get_response_schema(operation, spec),
                    parameters=_get_parameters(operation)
                )
                endpoints.append(endpoint)
        
        return endpoints
        
    except Exception as e:
        raise Exception(f"Failed to parse OpenAPI spec from {spec_url_or_path}: {str(e)}") from e

def _load_spec(spec_url_or_path: str) -> Dict[str, Any]:
    """Load specification from URL or file path."""
    if spec_url_or_path.startswith("http://") or spec_url_or_path.startswith("https://"):
        # Load from URL
        with urllib.request.urlopen(spec_url_or_path) as response:
            content = response.read().decode('utf-8')
            if spec_url_or_path.endswith(".json") or response.info().get_content_type() == "application/json":
                return json.loads(content)
            else:
                return yaml.safe_load(content)
    else:
        # Load from file
        with open(spec_url_or_path, 'r', encoding='utf-8') as file:
            if spec_url_or_path.endswith(".json"):
                return json.load(file)
            else:
                return yaml.safe_load(file)

def _get_request_content_type(operation: Dict[str, Any]) -> Optional[str]:
    """Extract request content type from operation."""
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    return next(iter(content.keys()), None) if content else None

def _get_response_content_type(operation: Dict[str, Any]) -> Optional[str]:
    """Extract response content type from operation (defaults to 200 response)."""
    responses = operation.get("responses", {})
    success_response = responses.get("200", responses.get("201", {}))
    content = success_response.get("content", {})
    return next(iter(content.keys()), None) if content else None

def _get_response_schema(operation: Dict[str, Any], spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract and resolve response schema from operation."""
    responses = operation.get("responses", {})
    success_response = responses.get("200", responses.get("201", {}))
    content = success_response.get("content", {})
    
    # Try to get schema from JSON content type first, then any available
    schema_def = None
    if "application/json" in content:
        schema_def = content["application/json"].get("schema")
    elif content:
        schema_def = next(iter(content.values()), {}).get("schema")
    
    if not schema_def:
        return None
        
    # Resolve $ref if present
    if "$ref" in schema_def:
        return _resolve_ref(schema_def["$ref"], spec)
    
    return schema_def

def _resolve_ref(ref: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve JSON Schema $ref reference within the specification.
    
    Args:
        ref: Reference string like "#/components/schemas/User"
        spec: Full OpenAPI specification
        
    Returns:
        Resolved schema dictionary
    """
    if not ref or not ref.startswith("#/"):
        return {}
    
    # Split reference path and navigate through spec
    path_parts = ref[2:].split("/")  # Remove "#/" prefix
    current = spec
    
    for part in path_parts:
        if not isinstance(current, dict) or part not in current:
            return {}
        current = current[part]
    
    return current if isinstance(current, dict) else {}

def _get_parameters(operation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract parameters from operation."""
    return operation.get("parameters", [])
