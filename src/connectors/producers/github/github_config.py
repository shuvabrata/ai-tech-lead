"""GitHub configuration loading and URL helpers.

This module is intentionally free of Neo4j dependencies so it can be
imported by the ActivitySignal producer container, which does not have
the ``neo4j`` package installed.
"""

from __future__ import annotations

import json
import os
import requests
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

from common.logger import logger


def load_config_from_server() -> Dict[str, Any]:
    """Load repository configuration from API server."""
    api_server = os.getenv("API_SERVER", "http://host.docker.internal:8000/")
    config_url = f"{api_server.rstrip('/')}/api/v1/connectors/github/configs"
    params = {"include_secrets": "true"}

    logger.info(f"Fetching configuration from {config_url} with params: {params}")
    try:
        response = requests.get(config_url, params=params, timeout=10)
        response.raise_for_status()

        raw_configs = response.json()

        # The API returns a list, but the app expects {"repos": [...]}
        transformed_configs: List[Dict[str, Any]] = []
        for raw_config in raw_configs:
            config_item: Dict[str, Any] = {
                "enabled": raw_config.get("enabled", True),
                "url": raw_config.get("url"),
                "access_token": raw_config.get("access_token"),
                "branch_name_patterns": raw_config.get("branch_name_patterns", []),
                "extraction_sources": raw_config.get("extraction_sources", []),
                "search_filters": raw_config.get("search_filters", {}),
            }
            transformed_configs.append(config_item)

        return {"repos": transformed_configs}

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch configuration from server: {e}")
        raise


def load_config_from_file() -> Dict[str, Any]:
    """Load repository configuration from .config.json."""
    config_path = Path(__file__).parent / ".config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], json.load(f))


def parse_repo_url(url: str) -> Tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.

    Example: ``https://github.com/owner/repo`` → ``('owner', 'repo')``
    Example: ``https://github.com/owner/*``    → ``('owner', '*')``
    """
    parts = url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def is_wildcard_url(url: str) -> bool:
    """Return True if *url* is a wildcard pattern (e.g. ``https://github.com/owner/*``)."""
    return url.rstrip("/").endswith("/*") or url.rstrip("/").endswith("%2F*")
