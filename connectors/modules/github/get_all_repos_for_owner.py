from typing import Dict, List, Optional
from github import Github, NamedUser
from github.Repository import Repository
from commons.logger import logger

def get_all_repos_for_owner(
    client: Github, 
    owner: str, 
    filters: Optional[Dict[str, str]] = None
) -> List[Repository]:
    """
    Get all repositories for a given owner (user or organization).
    
    Supports filtering using GitHub's search API.
    
    Args:
        client (Github): GitHub client instance
        owner (str): GitHub username or organization name
        filters (Optional[Dict[str, str]]): Search filters (key-value pairs)
            Example: {"props.asset-classification": "confidential", "props.application-context": "production"}
            Keys should include the "props." prefix for custom properties.

    Returns:
        List[Repository]: List of repository objects
    """
    repos: List[Repository] = []
    
    # If filters are specified, use search API
    if filters:
        try:
            # Build search query: "org:owner key1:value1 key2:value2"
            # Keys are used as-is (e.g., "props.property-name")
            query_parts = [f"org:{owner}"]
            for filter_key, filter_value in filters.items():
                query_parts.append(f"{filter_key}:{filter_value}")
            
            search_query = " ".join(query_parts)
            logger.info(f"Searching repositories with query: {search_query}")
            
            # Use GitHub search API
            search_results = client.search_repositories(query=search_query)
            repos = list(search_results)
            logger.info(f"Found {len(repos)} repositories matching filters for {owner}")
            
        except Exception as e:
            logger.error(f"Error searching repositories for {owner} with filters: {str(e)}")
            logger.exception(e)
    else:
        # No filters - use standard get_repos() method
        try:
            # Try as organization first
            org = client.get_organization(owner)
            repos = list(org.get_repos())
            logger.info(f"Found {len(repos)} repositories for organization: {owner}")
        except Exception:
            # If not an organization, try as user
            try:
                user = client.get_user(owner)
                repos = list(user.get_repos())
                logger.info(f"Found {len(repos)} repositories for user: {owner}")
            except Exception as e:
                logger.info(f"Error fetching repositories for {owner}: {str(e)}")
                logger.exception(e)

    return repos