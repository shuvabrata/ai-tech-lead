#!/usr/bin/env python3
"""
Jira Integration - Fetch Projects, Initiatives, Epics, Sprints, and Issues

This program connects to Jira, fetches projects, initiatives, epics, sprints, and all issue types,
and loads them into Neo4j with proper relationships.
"""
from typing import Any, Dict, Set, List, cast

import json
import requests
import os
from pathlib import Path
from datetime import datetime, timedelta
from atlassian import Jira
from neo4j import GraphDatabase

from neo4j_db.models import create_constraints
from modules.jira.new_project_handler import new_project_handler
from modules.jira.new_initiative_handler import new_initiative_handler
from modules.jira.new_epic_handler import new_epic_handler
from modules.jira.new_sprint_handler import new_sprint_handler
from modules.jira.new_issue_handler import new_issue_handler
from commons.person_cache import PersonCache
from commons.logger import logger

def load_config_from_server() -> Dict[str, Any]:
    """Load Jira configuration from API server."""
    api_server = os.getenv("API_SERVER", "http://host.docker.internal:8000/")
    config_url = f"{api_server.rstrip('/')}/api/v1/connectors/jira/configs"
    params = {"include_secrets": "true"}

    logger.info(f"Fetching configuration from {config_url} with params: {params}")
    try:
        response = requests.get(config_url, params=params, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

        # The API returns a list, but the app expects {"account": [...]}
        raw_configs = response.json()
        return {"account": raw_configs}

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch configuration from server: {e}")
        raise


def load_config_from_file() -> Dict[str, Any]:
    """Load configuration from .config.json file."""
    # Look for config file in the current directory or go up to find it
    config_path = Path(__file__).parent / '.config.json'
    if not config_path.exists():
        # Try parent directories
        config_path = Path(__file__).parent.parent.parent / '.config.json'

    if not config_path.exists():
        raise FileNotFoundError(f"Could not find .config.json file in {Path(__file__).parent} or its parent directories.")

    with open(config_path, 'r', encoding='utf-8') as f:
        return cast(Dict[str, Any], json.load(f))

def create_jira_connection(config: Dict[str, Any]) -> Jira:
    """Create and return a Jira connection object."""
    account = config['account'][0]  # Use first account
    
    jira = Jira(
        url=account['url'],
        username=account['email'],
        password=account['api_token'],
        cloud=True  # Set to True for Atlassian Cloud instances
    )
    
    # Validate connection
    user = jira.myself()  # type: ignore  # This will raise an exception if authentication fails
    if not user:
        raise Exception("Failed to authenticate with Jira. Please check your API credentials.")
    logger.info(f"Successfully authenticated as: {user.get('displayName', user.get('emailAddress', 'Unknown'))}")

    return jira


def fetch_projects(jira: Jira, max_results_per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch all projects from Jira using pagination."""
    try:
        logger.info("Fetching Jira projects...")
        
        all_projects = []
        start_at = 0
        
        while True:
            # Use the project search API
            # https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/#api-rest-api-3-project-search-get
            params = {
                'startAt': start_at,
                'maxResults': max_results_per_page
            }
            
            projects = jira.get('rest/api/3/project/search', params=params)
            
            if not projects or 'values' not in projects:
                break
            
            batch = projects['values']
            if not batch:
                break
            
            all_projects.extend(batch)
            logger.info(f"  Fetched {len(batch)} projects (total: {len(all_projects)})")
            
            # Check if there are more results
            total = projects.get('total', 0)
            if len(all_projects) >= total:
                break
            
            start_at += len(batch)
        
        logger.info(f"Found {len(all_projects)} total projects")
        return all_projects
    
    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        logger.exception(e)
        return []


def fetch_initiatives(jira: Jira, lookback_days: int = 90, max_results_per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch initiatives from Jira created in the last N days using pagination."""
    try:
        # Calculate the date N days ago
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
        
        jql = f'issuetype = Initiative AND created >= {cutoff_date_str} ORDER BY created DESC'
        
        logger.info(f"Fetching initiatives created since {cutoff_date_str}...")
        logger.info(f"Executing JQL: {jql}")
        
        all_initiatives = []
        next_page_token = None
        
        while True:
            # Use the enhanced_jql method for Jira Cloud
            response = jira.enhanced_jql(
                jql=jql,
                nextPageToken=next_page_token,
                limit=max_results_per_page
            )
            
            if not response or 'issues' not in response:
                break
            
            batch = response['issues']
            if not batch:
                break
            
            all_initiatives.extend(batch)
            logger.info(f"  Fetched {len(batch)} initiatives (total: {len(all_initiatives)})")
            
            # Check for next page token
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                # No more pages
                break
        
        logger.info(f"Found {len(all_initiatives)} total initiatives")
        return all_initiatives
    
    except Exception as e:
        logger.error(f"Error fetching initiatives: {e}")
        logger.exception(e)
        return []


def fetch_epics(jira: Jira, lookback_days: int = 90, max_results_per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch epics from Jira created in the last N days using pagination."""
    try:
        # Calculate the date N days ago
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
        
        jql = f'issuetype = Epic AND created >= {cutoff_date_str} ORDER BY created DESC'
        
        logger.info(f"Fetching epics created since {cutoff_date_str}...")
        logger.info(f"Executing JQL: {jql}")
        
        all_epics = []
        next_page_token = None
        
        while True:
            # Use the enhanced_jql method for Jira Cloud
            response = jira.enhanced_jql(
                jql=jql,
                nextPageToken=next_page_token,
                limit=max_results_per_page
            )
            
            if not response or 'issues' not in response:
                break
            
            batch = response['issues']
            if not batch:
                break
            
            all_epics.extend(batch)
            logger.info(f"  Fetched {len(batch)} epics (total: {len(all_epics)})")
            
            # Check for next page token
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                # No more pages
                break
        
        logger.info(f"Found {len(all_epics)} total epics")
        return all_epics
    
    except Exception as e:
        logger.error(f"Error fetching epics: {e}")
        logger.exception(e)
        return []


def extract_sprint_ids_from_issues(issues: List[Dict[str, Any]]) -> Set[str]:
    """Extract unique sprint IDs from issues.
    
    Args:
        issues: List of Jira issue objects
        
    Returns:
        Set of unique sprint IDs referenced by the issues
    """
    sprint_ids = set()
    
    for issue_data in issues:
        fields = issue_data.get('fields', {})
        
        # Extract sprint information from sprint field
        sprint_field = fields.get('sprint') or fields.get('customfield_10020', [])
        if sprint_field:
            # Handle both single sprint object and array of sprints
            sprints = sprint_field if isinstance(sprint_field, list) else [sprint_field]
            
            for sprint in sprints:
                if isinstance(sprint, dict):
                    sprint_id = sprint.get('id')
                    if sprint_id:
                        sprint_ids.add(str(sprint_id))
    
    return sprint_ids


def fetch_sprints_by_ids(jira: Jira, sprint_ids: Set[str]) -> List[Dict[str, Any]]:
    """Fetch specific sprints by their IDs.
    
    Args:
        jira: Jira connection object
        sprint_ids: Set of sprint IDs to fetch
        
    Returns:
        List of sprint objects
    """
    if not sprint_ids:
        logger.info("No sprint IDs to fetch")
        return []
    
    try:
        logger.info(f"Fetching {len(sprint_ids)} sprint(s) referenced by issues...")
        
        sprints = []
        fetched_count = 0
        failed_count = 0
        
        for sprint_id in sprint_ids:
            try:
                # Fetch individual sprint by ID
                sprint_response = jira.get(f'rest/agile/1.0/sprint/{sprint_id}')
                
                if sprint_response:
                    sprints.append(sprint_response)
                    fetched_count += 1
                    logger.debug(f"  ✓ Fetched sprint {sprint_id}: {sprint_response.get('name', 'Unknown')}")
                else:
                    logger.warning(f"  ✗ Sprint {sprint_id} not found")
                    failed_count += 1
                    
            except Exception as e:
                logger.warning(f"  ✗ Could not fetch sprint {sprint_id}: {e}")
                failed_count += 1
        
        logger.info(f"  ✓ Successfully fetched {fetched_count} sprint(s)")
        if failed_count > 0:
            logger.warning(f"  ✗ Failed to fetch {failed_count} sprint(s)")
        
        return sprints
        
    except Exception as e:
        logger.error(f"Error fetching sprints by IDs: {e}")
        logger.exception(e)
        return []


def fetch_issues(jira: Jira, lookback_days: int = 90, max_results_per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch all issues from Jira created in the last N days using pagination.
    
    Note: Excludes Initiative and Epic issue types as they are fetched separately.
    """
    try:
        # Calculate the date N days ago
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        cutoff_date_str = cutoff_date.strftime("%Y-%m-%d")
        
        # Exclude Initiatives and Epics since they're fetched separately
        jql = f'created >= {cutoff_date_str} AND issuetype NOT IN (Initiative, Epic) ORDER BY created DESC'

        #Todo: Find a way to store last sync date for issues and query only updates issues during incremental scan
        
        logger.info(f"Fetching issues (excluding Initiatives and Epics) created since {cutoff_date_str}...")
        logger.info(f"Executing JQL: {jql}")
        
        all_issues = []
        next_page_token = None
        
        while True:
            # Use the enhanced_jql method for Jira Cloud
            response = jira.enhanced_jql(
                jql=jql,
                nextPageToken=next_page_token,
                limit=max_results_per_page
            )
            
            if not response or 'issues' not in response:
                break
            
            batch = response['issues']
            if not batch:
                break
            
            all_issues.extend(batch)
            logger.info(f"  Fetched {len(batch)} issues (total: {len(all_issues)})")
            
            # Check for next page token
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                # No more pages
                break
        
        logger.info(f"Found {len(all_issues)} total issues")
        return all_issues
    
    except Exception as e:
        logger.error(f"Error fetching issues: {e}")
        logger.exception(e)
        return []


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
