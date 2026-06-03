"""Confluence configuration loading and connection helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, cast

import requests
from atlassian import Confluence  # type: ignore[import-untyped]

from common.logger import logger


def load_config_from_server() -> Dict[str, Any]:
    """Load Confluence connector configuration from the API server."""
    api_server = os.getenv("API_SERVER", "http://host.docker.internal:8000/")
    config_url = f"{api_server.rstrip('/')}/api/v1/connectors/confluence/configs"
    params = {"include_secrets": "true"}

    logger.info("Fetching Confluence configuration from %s", config_url)
    try:
        response = requests.get(config_url, params=params, timeout=10)
        response.raise_for_status()
        raw_configs = response.json()

        transformed_configs: List[Dict[str, Any]] = []
        for raw_config in raw_configs:
            transformed_configs.append(
                {
                    "id": raw_config.get("id"),
                    "enabled": raw_config.get("enabled", True),
                    "url": raw_config.get("url"),
                    "email": raw_config.get("email"),
                    "api_token": raw_config.get("api_token"),
                    "include_spaces": raw_config.get("include_spaces", []),
                    "exclude_spaces": raw_config.get("exclude_spaces", []),
                }
            )

        logger.info("Loaded %d Confluence configs from server", len(transformed_configs))
        return {"account": transformed_configs}
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to fetch Confluence configuration: %s", exc)
        raise


def load_config_from_file() -> Dict[str, Any]:
    """Load Confluence configuration from `.config.json`."""
    config_path = Path(__file__).parent / ".config.json"
    if not config_path.exists():
        config_path = Path(__file__).parent.parent.parent / ".config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Could not find .config.json file in {Path(__file__).parent} or its parent directories."
        )

    logger.info("Loading Confluence configuration from %s", config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = cast(Dict[str, Any], json.load(f))
    logger.debug("Loaded %d Confluence configs from file", len(config.get("account", [])))
    return config


def create_confluence_connection(config: Dict[str, Any]) -> Confluence:
    """Create and validate an authenticated Confluence connection."""
    account = config["account"][0]

    logger.info("Creating Confluence connection for url=%s", account["url"])
    confluence = Confluence(
        url=account["url"],
        username=account["email"],
        password=account["api_token"],
        cloud=True,
    )

    # Validate credentials with a lightweight read.
    logger.info("Validating Confluence credentials for url=%s", account["url"])
    confluence.get_all_spaces(start=0, limit=1)
    logger.info("Successfully authenticated to Confluence instance %s", account["url"])
    return confluence
