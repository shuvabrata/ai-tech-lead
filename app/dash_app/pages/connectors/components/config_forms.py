"""Connector config form specs."""

FIELD_TEXT = "text"
FIELD_PASSWORD = "password"
FIELD_NUMBER = "number"
FIELD_TEXTAREA = "textarea"
FIELD_CHECKBOX = "checkbox"
FIELD_MULTISELECT = "multiselect"

CONFIG_FORM_SPECS = {
    "github": {
        "connector_config": [
            {
                "key": "default_organization",
                "label": "Default Organization",
                "input_type": FIELD_TEXT,
                "placeholder": "my-org",
                "required": False,
            }
        ],
        "item": {
            "label": "Repository",
            "fields": [
                {
                    "key": "url",
                    "label": "Repository URL",
                    "input_type": FIELD_TEXT,
                    "placeholder": "https://github.com/org/repo",
                    "required": True,
                },
                {
                    "key": "access_token",
                    "label": "Access Token",
                    "input_type": FIELD_PASSWORD,
                    "placeholder": "ghp_...",
                    "required": False,
                    "secret": True,
                },
                {
                    "key": "branch_name_patterns",
                    "label": "Branch Name Patterns",
                    "input_type": FIELD_TEXTAREA,
                    "placeholder": "One regex per line",
                    "required": False,
                    "is_list": True,
                },
                {
                    "key": "extraction_sources",
                    "label": "Extraction Sources",
                    "input_type": FIELD_MULTISELECT,
                    "required": False,
                    "is_list": True,
                    "options": [
                        {"label": "Branch", "value": "branch"},
                        {"label": "Commit Message", "value": "commit_message"},
                    ],
                },
            ],
        },
    },
    "jira": {
        "connector_config": [],
        "item": {
            "label": "Jira Account",
            "fields": [
                {
                    "key": "url",
                    "label": "Jira Base URL",
                    "input_type": FIELD_TEXT,
                    "placeholder": "https://your-company.atlassian.net",
                    "required": True,
                },
                {
                    "key": "email",
                    "label": "Email",
                    "input_type": FIELD_TEXT,
                    "placeholder": "you@company.com",
                    "required": True,
                },
                {
                    "key": "api_token",
                    "label": "API Token",
                    "input_type": FIELD_PASSWORD,
                    "placeholder": "Jira API token",
                    "required": False,
                    "secret": True,
                },
            ],
        },
    },
    "slack": {
        "connector_config": [],
        "item": {
            "label": "Slack Channel",
            "fields": [
                {
                    "key": "channel_id",
                    "label": "Channel ID",
                    "input_type": FIELD_TEXT,
                    "placeholder": "C0123456789",
                    "required": True,
                },
                {
                    "key": "channel_name",
                    "label": "Channel Name",
                    "input_type": FIELD_TEXT,
                    "placeholder": "engineering",
                    "required": True,
                },
            ],
        },
    },
    "teams": {
        "connector_config": [],
        "item": {
            "label": "Teams Channel",
            "fields": [
                {
                    "key": "channel_id",
                    "label": "Channel ID",
                    "input_type": FIELD_TEXT,
                    "placeholder": "19:abc123@thread.tacv2",
                    "required": True,
                },
                {
                    "key": "channel_name",
                    "label": "Channel Name",
                    "input_type": FIELD_TEXT,
                    "placeholder": "product-updates",
                    "required": True,
                },
            ],
        },
    },
    "confluence": {
        "connector_config": [],
        "item": {
            "label": "Confluence Space",
            "fields": [
                {
                    "key": "space_key",
                    "label": "Space Key",
                    "input_type": FIELD_TEXT,
                    "placeholder": "ENG",
                    "required": True,
                },
                {
                    "key": "space_name",
                    "label": "Space Name",
                    "input_type": FIELD_TEXT,
                    "placeholder": "Engineering",
                    "required": True,
                },
            ],
        },
    },
    "google_docs": {
        "connector_config": [],
        "item": {
            "label": "Google Drive",
            "fields": [
                {
                    "key": "drive_id",
                    "label": "Drive ID",
                    "input_type": FIELD_TEXT,
                    "placeholder": "0AAbC1234xyz",
                    "required": True,
                },
                {
                    "key": "drive_name",
                    "label": "Drive Name",
                    "input_type": FIELD_TEXT,
                    "placeholder": "Team Drive",
                    "required": True,
                },
            ],
        },
    },
    "sharepoint": {
        "connector_config": [],
        "item": {
            "label": "SharePoint Site",
            "fields": [
                {
                    "key": "site_url",
                    "label": "Site URL",
                    "input_type": FIELD_TEXT,
                    "placeholder": "https://company.sharepoint.com/sites/eng",
                    "required": True,
                }
            ],
        },
    },
    "email": {
        "connector_config": [],
        "item": {
            "label": "Email Account",
            "fields": [
                {
                    "key": "smtp_host",
                    "label": "SMTP Host",
                    "input_type": FIELD_TEXT,
                    "placeholder": "smtp.company.com",
                    "required": True,
                },
                {
                    "key": "smtp_port",
                    "label": "SMTP Port",
                    "input_type": FIELD_NUMBER,
                    "placeholder": "587",
                    "required": True,
                },
                {
                    "key": "imap_host",
                    "label": "IMAP Host",
                    "input_type": FIELD_TEXT,
                    "placeholder": "imap.company.com",
                    "required": True,
                },
                {
                    "key": "imap_port",
                    "label": "IMAP Port",
                    "input_type": FIELD_NUMBER,
                    "placeholder": "993",
                    "required": True,
                },
                {
                    "key": "username",
                    "label": "Username",
                    "input_type": FIELD_TEXT,
                    "placeholder": "you@company.com",
                    "required": True,
                },
                {
                    "key": "use_tls",
                    "label": "Use TLS",
                    "input_type": FIELD_CHECKBOX,
                    "required": True,
                },
                {
                    "key": "password",
                    "label": "Password",
                    "input_type": FIELD_PASSWORD,
                    "placeholder": "Email password",
                    "required": False,
                    "secret": True,
                },
            ],
        },
    },
}
