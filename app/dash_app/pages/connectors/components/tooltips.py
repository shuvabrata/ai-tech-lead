"""Tooltip descriptions for connector configuration fields."""

from typing import Dict

FIELD_TOOLTIPS: Dict[str, Dict[str, str]] = {
    "github": {
        "url": "The full URL of the GitHub repository (e.g., https://github.com/owner/repo).",
        "access_token": "A personal access token with read permissions for the repository.",
        "branch_name_patterns": "Custom regular expressions used to find Jira keys inside branch names. Each pattern must contain exactly one capture group () around the Jira key. If left blank, it defaults to standard Git Flow (e.g., feature/(PROJ-123)-desc) and prefix patterns (e.g., (PROJ-123)-desc).",
        "extraction_sources": "Select where the system should look for Jira ticket keys (e.g., PROJ-123) to link your code changes to work items. You can choose to extract keys from the branch name, the commit message, or both.",
    },
    "jira": {
        "url": "The base URL of your Jira instance (e.g., https://your-domain.atlassian.net).",
        "email": "The email address associated with your Jira account.",
        "api_token": "Your Jira API token for authentication.",
    },
    "slack": {
        "channel_id": "The unique identifier of the Slack channel (e.g., C12345678).",
        "channel_name": "The display name of the Slack channel (e.g., #general).",
    },
    "teams": {
        "channel_id": "The unique identifier for the Microsoft Teams channel.",
        "channel_name": "The display name of the Microsoft Teams channel.",
    },
    "confluence": {
        "space_key": "The unique key of the Confluence space (e.g., ENG).",
        "space_name": "The display name of the Confluence space.",
    },
    "google_docs": {
        "drive_id": "The unique identifier of the Google Drive or Shared Drive.",
        "drive_name": "The display name of the Google Drive.",
    },
    "sharepoint": {
        "site_url": "The full URL to the SharePoint site.",
    },
    "email": {
        "smtp_host": "The hostname of your SMTP server for outgoing emails.",
        "smtp_port": "The port number for your SMTP server (e.g., 587 or 465).",
        "imap_host": "The hostname of your IMAP server for incoming emails.",
        "imap_port": "The port number for your IMAP server (e.g., 993).",
        "username": "The username or email address used for authentication.",
        "use_tls": "Toggle to enable TLS encryption for the connection.",
        "password": "The password or app-specific password for the email account.",
    },
}