"""GitHub, Jira, and Confluence producers for the ActivitySignal event-driven ingestion pipeline.

Each producer lives in its own package under ``producers/``:

- ``producers/github/`` — GitHub producer (main.py + fetch_github.py + map_github.py + helpers)
- ``producers/jira/``   — Jira producer (main.py + fetch_jira.py + map_jira.py + jira_config.py)
- ``producers/confluence/`` — Confluence producer (main.py + helpers)

Shared utilities (``sync_cursor.py``) live at the package root.
"""
