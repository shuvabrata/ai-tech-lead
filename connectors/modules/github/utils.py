import os
from typing import Dict, Any

from github import Github


def get_github_client(repo_config: Dict[str, Any]) -> Github:
    """
    Get GitHub client with appropriate authentication.

    Uses repo-specific token if provided, otherwise falls back to 
    GITHUB_TOKEN_FOR_PUBLIC_REPOS environment variable.

    Args:
        repo_config (Dict[str, Any]): Repository configuration containing access token.

    Returns:
        Github: Authenticated GitHub client instance.

    Raises:
        ValueError: If no GitHub token is found in the configuration or environment variable.
    """
    token= repo_config.get('access_token')

    if not token:
        token = os.getenv('GITHUB_TOKEN_FOR_PUBLIC_REPOS')

    if not token:
        raise ValueError("No GitHub token found. Please provide token in config or set GITHUB_TOKEN_FOR_PUBLIC_REPOS")

    return Github(token)
