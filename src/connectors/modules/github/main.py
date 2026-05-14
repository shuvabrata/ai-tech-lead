#!/usr/bin/env python3
"""
.. deprecated::
    This module is the **legacy** direct-to-Neo4j GitHub ingestion entrypoint.
    It will be removed once the event-driven pipeline
    (``connectors/producers/github_producer.py`` → RabbitMQ →
    ``connectors/consumers/``) is proven stable in production.

    Do **not** add new features here.  All new work should target the
    producer/consumer pipeline instead.

GitHub Repository Information Fetcher

Loads repository URLs from .config.json or a config server and fetches repository properties
using the GitHub API.
"""

import os
from pathlib import Path
from typing import Dict, List, Any
from neo4j import GraphDatabase
from connectors.neo4j_db.models import (
    create_constraints
)
from connectors.modules.github.get_all_repos_for_owner import get_all_repos_for_owner
from connectors.modules.github.process_repo import process_repo
from connectors.modules.github.utils import get_github_client
from connectors.commons.config_validator import validate_config
from connectors.commons.logger import logger
from connectors.modules.github.github_config import (
    is_wildcard_url,
    load_config_from_file,
    load_config_from_server,
    parse_repo_url,
)

def main() -> None:
    """Main execution function"""
    import warnings
    warnings.warn(
        "connectors.modules.github.main is deprecated and will be removed. "
        "Use connectors.producers.github_producer (event-driven pipeline) instead.",
        DeprecationWarning,
        stacklevel=1,
    )
    logger.warning(
        "[DEPRECATED] connectors/modules/github/main.py is the legacy direct-to-Neo4j "
        "entrypoint. Migrate to connectors/producers/github_producer.py."
    )
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
