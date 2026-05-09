#!/usr/bin/env python3
"""
Jira Integration - Fetch Projects, Initiatives, Epics, Sprints, and Issues

This program connects to Jira, fetches projects, initiatives, epics, sprints, and all issue types,
and loads them into Neo4j with proper relationships.
"""
from typing import Any, Dict, Set, List

import os
from atlassian import Jira
from neo4j import GraphDatabase

from connectors.neo4j_db.models import create_constraints
from connectors.modules.jira.new_project_handler import new_project_handler
from connectors.modules.jira.new_initiative_handler import new_initiative_handler
from connectors.modules.jira.new_epic_handler import new_epic_handler
from connectors.modules.jira.new_sprint_handler import new_sprint_handler
from connectors.modules.jira.new_issue_handler import new_issue_handler
from connectors.commons.person_cache import PersonCache
from connectors.commons.logger import logger
from connectors.modules.jira.jira_config import (
    create_jira_connection,
    load_config_from_file,
    load_config_from_server,
)
from connectors.producers.fetch_jira import (
    fetch_projects,
    fetch_initiatives,
    fetch_epics,
    fetch_sprints_by_ids,
    fetch_issues,
)
from connectors.producers.map_jira import extract_sprint_ids_from_issues


















def main() -> int:
    """Main function to run the Jira integration."""
    try:
        logger.info("=" * 80)
        logger.info("Jira Integration - Full Data Loader")
        logger.info("=" * 80)
        
        config: Dict[str, Any]
        config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()

        try:
            if config_source == "SERVER":
                logger.info("\nLoading configuration from SERVER...")
                config = load_config_from_server()
            else:
                logger.info("\nLoading configuration from FILE...")
                config = load_config_from_file()

        except FileNotFoundError as e:
            logger.error(f"Configuration file not found. Please create .config.json or set CONFIGURATION_SOURCE=SERVER.")
            logger.exception(e)
            return 1
        except Exception as e:
            logger.error(f"A critical error occurred during configuration loading: {e}")
            logger.exception(e)
            return 1

        # Get lookback days from environment variable
        lookback_days = int(os.getenv('JIRA_LOOKBACK_DAYS', '90'))
        logger.info(f"Using lookback period: {lookback_days} days")
        
        # Get max results per page from environment variable
        max_results_per_page = int(os.getenv('JIRA_MAX_RESULTS_PER_PAGE', '100'))
        logger.info(f"Using max results per page: {max_results_per_page}")
        
        # Connect to Jira
        logger.info(f"\nConnecting to Jira: {config['account'][0]['url']}")
        jira = create_jira_connection(config)
        
        # Initialize Neo4j connection
        neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
        neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
        
        logger.info(f"\nConnecting to Neo4j at {neo4j_uri}...")
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        
        try:
            # Verify Neo4j connection
            driver.verify_connectivity()
            logger.info("✓ Neo4j connection established")
            
            # Create constraints for layers 1 (Person, IdentityMapping), 2 (Project, Initiative), 3 (Epic), 4 (Issue, Sprint)
            logger.info("\nCreating database constraints...")
            with driver.session() as session:
                create_constraints(session, layers=[1, 2, 3, 4])
            logger.info("✓ Constraints created")
            
            # Counters for tracking
            projects_processed = 0
            projects_failed = 0
            initiatives_processed = 0
            initiatives_failed = 0
            epics_processed = 0
            epics_failed = 0
            sprints_processed = 0
            sprints_failed = 0
            issues_processed = 0
            issues_failed = 0
            project_id_map: Dict[str, str] = {}  # Map Jira project key to Neo4j project ID
            initiative_id_map: Dict[str, str] = {}  # Map Jira issue ID to Neo4j initiative ID
            epic_id_map: Dict[str, str] = {}  # Map Jira issue ID to Neo4j epic ID
            sprint_id_map: Dict[str, str] = {}  # Map Jira sprint ID to Neo4j sprint ID
            processed_epics: Set[str] = set()  # Track processed epic IDs to avoid duplicates
            
            # Extract base URL from config for constructing browse URLs
            jira_base_url = config['account'][0]['url'].rstrip('/')
            
            # Create PersonCache for all user processing (significant performance improvement)
            # Single cache used across initiatives, epics, and issues for maximum cache hit rate
            person_cache = PersonCache()
            
            # Fetch and process projects
            logger.info("\n%s", "=" * 80)
            logger.info("PROCESSING PROJECTS")
            logger.info("=" * 80)
            
            projects = fetch_projects(jira, max_results_per_page=max_results_per_page)
            
            with driver.session() as session:
                for project_data in projects:
                    try:
                        project_id = new_project_handler(session, project_data, person_cache, jira_base_url=jira_base_url)
                        if project_id:
                            project_key = str(project_data.get('key'))
                            project_id_map[project_key] = project_id
                            projects_processed += 1
                        else:
                            projects_failed += 1
                    except Exception as e:
                        logger.error(f"  ✗ Error processing project: {str(e)}")
                        logger.exception(e)
                        projects_failed += 1
            
            # Fetch and process initiatives
            logger.info("\n%s", "=" * 80)
            logger.info("PROCESSING INITIATIVES")
            logger.info("=" * 80)
            
            initiatives = fetch_initiatives(jira, lookback_days=lookback_days, max_results_per_page=max_results_per_page)
            
            with driver.session() as session:
                for initiative_data in initiatives:
                    try:
                        initiative_id = new_initiative_handler(
                            session, 
                            initiative_data, 
                            project_id_map,
                            person_cache,
                            jira_connection=jira,
                            jira_base_url=jira_base_url,
                            initiative_id_map=initiative_id_map,
                            processed_epics=processed_epics
                        )
                        if initiative_id:
                            # Store initiative ID in map
                            jira_initiative_id = initiative_data.get('id')
                            if jira_initiative_id:
                                initiative_id_map[jira_initiative_id] = initiative_id
                            initiatives_processed += 1
                        else:
                            initiatives_failed += 1
                    except Exception as e:
                        logger.error(f"  ✗ Error processing initiative: {str(e)}")
                        logger.exception(e)
                        initiatives_failed += 1
            
            # Count epics processed as children of initiatives
            epics_from_initiatives = len(processed_epics)
            if epics_from_initiatives > 0:
                logger.info(f"\n  ✓ Processed {epics_from_initiatives} epic(s) as children of initiatives")
                epics_processed += epics_from_initiatives
            
            # Print summary
            logger.info("\n" + "=" * 80)
            logger.info("SUMMARY")
            logger.info("=" * 80)
            logger.info(f"\nProjects:")
            logger.info(f"  ✓ Successfully processed: {projects_processed}")
            logger.info(f"  ✗ Failed: {projects_failed}")
            logger.info(f"  Total: {projects_processed + projects_failed}")
            
            logger.info(f"\nInitiatives:")
            logger.info(f"  ✓ Successfully processed: {initiatives_processed}")
            logger.info(f"  ✗ Failed: {initiatives_failed}")
            logger.info(f"  Total: {initiatives_processed + initiatives_failed}")
            
            # Fetch and process epics (catches any epics not linked to initiatives)
            logger.info("\n" + "="*80)
            logger.info("PROCESSING EPICS")
            logger.info("="*80)
            
            epics = fetch_epics(jira, lookback_days=lookback_days, max_results_per_page=max_results_per_page)
            
            standalone_epics_count = 0
            with driver.session() as session:
                for epic_data in epics:
                    try:
                        epic_id = new_epic_handler(
                            session,
                            epic_data,
                            initiative_id_map,
                            person_cache,
                            jira_base_url=jira_base_url,
                            processed_epics=processed_epics
                        )
                        if epic_id:
                            # Check if this was a new epic (not processed as child)
                            epic_jira_id = epic_data.get('id')
                            if epic_jira_id:
                                epic_id_map[epic_jira_id] = epic_id
                            if epic_jira_id not in processed_epics or len(processed_epics) == epics_processed:
                                standalone_epics_count += 1
                        else:
                            epics_failed += 1
                    except Exception as e:
                        logger.error(f"  ✗ Error processing epic: {str(e)}")
                        logger.exception(e)
                        epics_failed += 1
            
            epics_processed += standalone_epics_count
            if standalone_epics_count > 0:
                logger.info(f"\n  ✓ Processed {standalone_epics_count} standalone epic(s) (not linked to initiatives)")
            
            logger.info(f"\nEpics:")
            logger.info(f"  ✓ Successfully processed: {epics_processed}")
            logger.info(f"  ✗ Failed: {epics_failed}")
            logger.info(f"  Total: {epics_processed + epics_failed}")
            
            # Fetch issues first to determine which sprints we need
            logger.info("\n" + "=" * 80)
            logger.info("FETCHING ISSUES")
            logger.info("=" * 80)
            
            issues = fetch_issues(jira, lookback_days=lookback_days, max_results_per_page=max_results_per_page)
            
            # Extract sprint IDs from issues
            logger.info("\n" + "=" * 80)
            logger.info("EXTRACTING SPRINT REFERENCES")
            logger.info("=" * 80)
            
            sprint_ids = extract_sprint_ids_from_issues(issues)
            logger.info(f"Found {len(sprint_ids)} unique sprint(s) referenced by issues")
            
            # Fetch only the sprints that are referenced by issues
            logger.info("\n" + "=" * 80)
            logger.info("PROCESSING SPRINTS")
            logger.info("=" * 80)
            
            sprints = fetch_sprints_by_ids(jira, sprint_ids)
            
            with driver.session() as session:
                for sprint_data in sprints:
                    try:
                        sprint_id = new_sprint_handler(
                            session,
                            sprint_data,
                            jira_base_url=jira_base_url
                        )
                        if sprint_id:
                            # Store sprint ID in map
                            jira_sprint_id = str(sprint_data.get('id'))
                            if jira_sprint_id:
                                sprint_id_map[jira_sprint_id] = sprint_id
                            sprints_processed += 1
                        else:
                            sprints_failed += 1
                    except Exception as e:
                        logger.error(f"  ✗ Error processing sprint: {str(e)}")
                        logger.exception(e)
                        sprints_failed += 1
            
            # Process issues (all types)
            logger.info("\n%s" + "=" * 80)
            logger.info("PROCESSING ISSUES")
            logger.info("=" * 80)
            
            # Count by type
            issue_type_counts: Dict[str, int] = {}
            
            logger.info(f"Processing {len(issues)} issue(s)...")
            
            with driver.session() as session:
                for issue_data in issues:
                    try:
                        issue_id = new_issue_handler(
                            session,
                            issue_data,
                            epic_id_map,
                            sprint_id_map,
                            person_cache,
                            jira_base_url=jira_base_url
                        )
                        if issue_id:
                            # Count by type
                            issue_type = issue_data.get('fields', {}).get('issuetype', {}).get('name', 'Unknown')
                            issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
                            issues_processed += 1
                        else:
                            issues_failed += 1
                    except Exception as e:
                        logger.error(f"  ✗ Error processing issue: {str(e)}")
                        logger.exception(e)
                        issues_failed += 1
                
                # Flush PersonCache after processing all entities (initiatives, epics, issues)
                # This batches all IdentityMapping writes for maximum efficiency
                try:
                    person_cache.flush_identity_mappings(session)
                    
                    # Log cache statistics
                    stats = person_cache.get_stats()
                    logger.info(f"\n  📊 PersonCache stats (all entities): {stats['cache_hits']} hits, {stats['cache_misses']} misses, hit rate: {stats['hit_rate']}")
                except Exception as e:
                    logger.info(f"  Warning: Could not flush PersonCache - {str(e)}")
            
            if issues_processed > 0:
                logger.info(f"\n  ✓ Processed {issues_processed} issue(s):")
                for issue_type, count in issue_type_counts.items():
                    if count > 0:
                        logger.info(f"     - {issue_type}: {count}")
            
            # Print final summary
            logger.info("\n" + "=" * 80)
            logger.info("FINAL SUMMARY")
            logger.info("=" * 80)
            logger.info(f"\nProjects:")
            logger.info(f"  ✓ Successfully processed: {projects_processed}")
            logger.info(f"  ✗ Failed: {projects_failed}")
            logger.info(f"  Total: {projects_processed + projects_failed}")
            
            logger.info(f"\nInitiatives:")
            logger.info(f"  ✓ Successfully processed: {initiatives_processed}")
            logger.info(f"  ✗ Failed: {initiatives_failed}")
            logger.info(f"  Total: {initiatives_processed + initiatives_failed}")
            
            logger.info(f"\nEpics:")
            logger.info(f"  ✓ Successfully processed: {epics_processed}")
            logger.info(f"  ✗ Failed: {epics_failed}")
            logger.info(f"  Total: {epics_processed + epics_failed}")
            
            logger.info(f"\nSprints:")
            logger.info(f"  ✓ Successfully processed: {sprints_processed}")
            logger.info(f"  ✗ Failed: {sprints_failed}")
            logger.info(f"  Total: {sprints_processed + sprints_failed}")
            
            logger.info(f"\nIssues:")
            logger.info(f"  ✓ Successfully processed: {issues_processed}")
            for issue_type, count in issue_type_counts.items():
                if count > 0:
                    logger.info(f"     - {issue_type}: {count}")
            logger.info(f"  ✗ Failed: {issues_failed}")
            logger.info(f"  Total: {issues_processed + issues_failed}")
            
        finally:
            # Close Neo4j connection
            driver.close()
            logger.info("\n✓ Neo4j connection closed")
        
        return 0
        
    except Exception as e:
        logger.error(f"\n✗ Fatal error: {str(e)}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    exit(main())
