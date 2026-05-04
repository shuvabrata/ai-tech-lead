#!/usr/bin/env python3
"""
GitHub Repository Information Fetcher

Loads repository URLs from .config.json or a config server and fetches repository properties
using the GitHub API.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, cast

import requests
from neo4j import GraphDatabase
from connectors.neo4j_db.models import (
    create_constraints
)
from connectors.modules.github.get_all_repos_for_owner import get_all_repos_for_owner
from connectors.modules.github.process_repo import process_repo
from connectors.modules.github.utils import get_github_client
from connectors.commons.config_validator import validate_config

from connectors.commons.logger import logger


def load_config_from_server() -> Dict[str, Any]:
    """Load repository configuration from API server."""
    api_server = os.getenv("API_SERVER", "http://host.docker.internal:8000/")
    config_url = f"{api_server.rstrip('/')}/api/v1/connectors/github/configs"
    params = {"include_secrets": "true"}

    logger.info(f"Fetching configuration from {config_url} with params: {params}")
    try:
        response = requests.get(config_url, params=params, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

        raw_configs = response.json()

        # The API returns a list, but the app expects {"repos": [...]}
        # Also, the token key is "access_token" in API, but "token" is expected.
        transformed_configs = []
        for raw_config in raw_configs:
            config_item = {
                "url": raw_config.get("url"),
                "access_token": raw_config.get("access_token"),
                "branch_name_patterns": raw_config.get("branch_name_patterns", []),
                "extraction_sources": raw_config.get("extraction_sources", []),
                "search_filters": raw_config.get("search_filters", {})
            }
            transformed_configs.append(config_item)

        return {"repos": transformed_configs}

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch configuration from server: {e}")
        raise


def load_config_from_file() -> Dict[str, Any]:
    """Load repository configuration from .config.json"""
    config_path = Path(__file__).parent / ".config.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        return cast(Dict[str, Any], json.load(f))

def parse_repo_url(url: str) -> Tuple[str, str]:
    """
    Extract owner and repo name from GitHub URL.

    Example: https://github.com/owner/repo -> (owner, repo)
    Example: https://github.com/owner/* -> (owner, *)
    
    Args:
        url (str): The GitHub repository URL.

    Returns:
        Tuple[str, str]: A tuple containing the owner and repository name.
    """
    parts = url.rstrip('/').split('/')
    return parts[-2], parts[-1]

def is_wildcard_url(url: str) -> bool:
    """
    Check if the URL is a wildcard pattern (e.g., https://github.com/owner/*)

    Args:
        url (str): The GitHub repository URL.

    Returns:
        bool: True if the URL is a wildcard pattern, False otherwise.
    """
    return url.rstrip('/').endswith('/*') or url.rstrip('/').endswith('%2F*')

def main() -> None:
    """Main execution function"""
    logger.info("GitHub Repository Information Fetcher")
    logger.info("=" * 50)

    config: Dict[str, Any]
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()

    try:
        if config_source == "SERVER":
            logger.info("Configuration source: SERVER")
            config = load_config_from_server()
            # Skipping file-based validation for server config
            logger.info("Skipping file-based validation for server-provided configuration.")
        else:
            logger.info("Configuration source: FILE")
            config_path = Path(__file__).parent / ".config.json"

            # Validate configuration file exists and is valid
            if not config_path.is_file():
                logger.error(f"Configuration file not found: {config_path}")
                logger.error("Please create it from the .config.example.json template or set CONFIGURATION_SOURCE=SERVER.")
                return

            if not validate_config(str(config_path), config_type="github"):
                logger.error("Configuration validation failed. Please fix errors and try again.")
                return

            config = load_config_from_file()

    except Exception as e:
        logger.error(f"A critical error occurred during configuration loading: {e}")
        logger.exception(e)
        return
        
    # Initialize Neo4j connection
    neo4j_uri: str = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user: str = os.getenv('NEO4J_USERNAME', 'neo4j')
    neo4j_password: str = os.getenv('NEO4J_PASSWORD', 'password')

    logger.info(f"\nConnecting to Neo4j at {neo4j_uri}...")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    try:
        # Verify connection
        driver.verify_connectivity()
        logger.info("✓ Neo4j connection established\n")

        # Create constraints for layers 1 (Person, Team, IdentityMapping), 5 (Repository), 6 (Branch), 7 (Commit, File), and 8 (PullRequest)
        logger.info("Creating database constraints...")
        with driver.session() as session:
            create_constraints(session, layers=[1, 5, 6, 7, 8])
        logger.info("✓ Constraints created\n")

        logger.info(f"Loaded {len(config.get('repos', []))} repositories from config\n")

        # Counters for tracking
        repos_processed: int = 0
        repos_failed: int = 0

        # Create a session for the entire operation
        with driver.session() as session:
            # Process each repository
            for idx, repo_config in enumerate(config.get('repos', []), 1):
                repo_url: str = repo_config['url']
                logger.info(f"\n[{idx}] Processing: {repo_url}")
                logger.info("-" * 50)

                try:
                    # Get GitHub client
                    client = get_github_client(repo_config)

                    # Check if this is a wildcard URL (e.g., https://github.com/owner/*)
                    if is_wildcard_url(repo_url):
                        # Extract owner and enumerate all repos
                        owner, _ = parse_repo_url(repo_url)
                        logger.info(f"Wildcard pattern detected. Fetching all repositories for: {owner}")

                        # Extract filters if provided
                        filters = repo_config.get('search_filters')
                        repos: List[Any] = get_all_repos_for_owner(client, owner, filters)

                        for repo in repos:
                            try:
                                # Process repository (creates nodes and relationships)
                                logger.info(f"\n  ↳ {repo.name}")
                                process_repo(repo, session, repo_config, github_obj=client)
                                repos_processed += 1

                            except Exception as e:
                                logger.info(f"    ✗ Error processing {repo.name}: {str(e)}")
                                logger.exception(e)
                                repos_failed += 1
                                continue

                    else:
                        # Single repository
                        # Parse URL and get repository
                        owner, repo_name = parse_repo_url(repo_url)
                        repo = client.get_repo(f"{owner}/{repo_name}")

                        # Process repository (creates nodes and relationships)
                        process_repo(repo, session, repo_config, github_obj=client)
                        repos_processed += 1

                except Exception as e:
                    logger.info(f"✗ Error: {str(e)}")
                    logger.exception(e)
                    repos_failed += 1
                    continue

        logger.info("\n" + "=" * 50)
        logger.info("\nSummary:")
        logger.info(f"  ✓ Successfully processed: {repos_processed}")
        logger.info(f"  ✗ Failed: {repos_failed}")
        logger.info(f"  Total: {repos_processed + repos_failed}")

    finally:
        # Close Neo4j connection
        driver.close()
        logger.info("\n✓ Neo4j connection closed")

if __name__ == "__main__":
    main()
