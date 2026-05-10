"""Jira configuration loading and connection helpers.

This module is intentionally free of Neo4j dependencies so it can be
imported by the ActivitySignal producer container, which does not have
the ``neo4j`` package installed.
"""

from __future__ import annotations

import json
import os
import requests
from pathlib import Path
from typing import Any, Dict, cast

from atlassian import Jira  # type: ignore[import-untyped]

from connectors.commons.logger import logger


def load_config_from_server() -> Dict[str, Any]:
    """Load Jira configuration from API server."""
    api_server = os.getenv("API_SERVER", "http://host.docker.internal:8000/")
    config_url = f"{api_server.rstrip('/')}/api/v1/connectors/jira/configs"
    params = {"include_secrets": "true"}

    logger.info(f"Fetching configuration from {config_url} with params: {params}")
    try:
        response = requests.get(config_url, params=params, timeout=10)
        response.raise_for_status()

        # The API returns a list, but the app expects {"account": [...]}
        raw_configs = response.json()
        return {"account": raw_configs}

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch configuration from server: {e}")
        raise


def load_config_from_file() -> Dict[str, Any]:
    """Load configuration from .config.json file."""
    config_path = Path(__file__).parent / ".config.json"
    if not config_path.exists():
        config_path = Path(__file__).parent.parent.parent / ".config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Could not find .config.json file in {Path(__file__).parent} "
            "or its parent directories."
        )

    with open(config_path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], json.load(f))


def create_jira_connection(config: Dict[str, Any]) -> Jira:
    """Create and return an authenticated Jira connection object."""
    account = config["account"][0]

    jira = Jira(
        url=account["url"],
        username=account["email"],
        password=account["api_token"],
        cloud=True,
    )

    # Validate connection — raises if credentials are wrong
    user = jira.myself()  # type: ignore[union-attr]
    if not user:
        raise RuntimeError(
            "Failed to authenticate with Jira. Please check your API credentials."
        )
    logger.info(
        f"Successfully authenticated as: "
        f"{user.get('displayName', user.get('emailAddress', 'Unknown'))}"
    )

    return jira
