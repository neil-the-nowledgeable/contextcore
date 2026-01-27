#!/usr/bin/env python3
"""
CLI for Rabbit webhook server.

Usage:
    python -m contextcore_rabbit.cli --port 8082
    contextcore-rabbit --port 8082
"""

import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def main():
    parser = argparse.ArgumentParser(
        description="Rabbit (Waabooz) - Alert-Triggered Automation Server"
    )
    parser.add_argument(
        "--port", type=int, default=8082,
        help="Port to listen on (default: 8082)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable debug mode"
    )

    args = parser.parse_args()

    # Import here to ensure actions are registered
    from contextcore_rabbit import WebhookServer
    from contextcore_rabbit import actions  # noqa: F401 - registers actions

    server = WebhookServer(port=args.port, host=args.host)
    server.run(debug=args.debug)


if __name__ == "__main__":
    main()
