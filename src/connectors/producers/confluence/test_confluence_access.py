## All helpers are now imported from their respective modules
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set, Tuple

# Import directly, relying on PYTHONPATH
from common.activity_signal.models import ActivitySignal, PersonAttributes, Relationship, RelationshipTarget


from atlassian import Confluence
import requests

from connectors.producers.confluence.confluence_helpers import (
    get_spaces,
    get_recent_content,
    process_content_body,
    get_comments,
    get_user_details_async
)
from connectors.producers.confluence.parse_body_for_relations import parse_body_for_relations



def build_person_signal(user_data: Dict[str, Any], account_id: str, confluence_url: str) -> ActivitySignal:
    """Build an ActivitySignal for a Person with source='atlassian'."""
    email = user_data.get("email")
    public_name = user_data.get("publicName")
    display_name = user_data.get("displayName")
    full_name = public_name or display_name or account_id

    attrs = PersonAttributes(
        full_name=full_name,
        account_id=account_id,
        email=email
    )
    
    return ActivitySignal(
        source="atlassian",
        id=account_id,
        source_config=confluence_url,
        connector_url="https://wba-ai/connectors/confluence/test",
        event_time=datetime.now(timezone.utc),
        version="1.0",
        attributes=attrs
    )

# ---------------------------------------------------------------------------
# Main Async Workflow
# ---------------------------------------------------------------------------

async def main_async():
    print("=== Confluence Connector Prep Script ===")
    config_path = os.path.join(os.path.dirname(__file__), '.config.json')
    
    if not os.path.exists(config_path):
        print(f"❌ Error: Configuration file not found at {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = json.load(f)

    accounts = config.get("account", [])
    if not accounts:
        print("❌ Error: No accounts found in .config.json")
        sys.exit(1)

    account = accounts[0]
    url = account.get("url")
    email = account.get("email")
    api_token = account.get("api_token")

    confluence = Confluence(
        url=url,
        username=email,
        password=api_token,
        cloud=True
    )

    print(f"\n1. Authenticating to {url}...")
    
    # 1. Fetch Spaces
    print("\n2. Fetching Spaces...")
    spaces = await get_spaces(confluence, limit=50)
    print(f"✅ Retrieved {len(spaces)} spaces:")
    for space in spaces:
        print(f"\n   [SPACE]")
        print(f"     - key: {space.get('key')}")
        print(f"     - name: {space.get('name')}")
        print(f"     - type: {space.get('type')}")
        print(f"     - url: {space.get('_links', {}).get('webui')}")
        
    # 2. Fetch Recent Pages/Blogposts via CQL
    # Look back 30 days for this test
    lookback = datetime.now(timezone.utc) - timedelta(days=30)
    print(f"\n3. Fetching Recent Content via CQL (since {lookback.strftime('%Y-%m-%d')})...")
    
    recent_items = await get_recent_content(confluence, lookback, limit=50)
    print(f"✅ Retrieved {len(recent_items)} recent items:")
    
    all_mentioned_account_ids = set()

    # 3. Process Bodies for Mentions and Jira Links
    for item in recent_items:
        # CQL results sometimes wrap the actual entity in a 'content' field
        content = item.get('content', item)
        
        content_id = content.get('id')
        ctype = content.get('type', 'unknown').capitalize()
        title = content.get('title')
        status = content.get('status')
        url_suffix = content.get('_links', {}).get('webui')
        
        history = content.get('history', {})
        created_at = history.get('createdDate', 'Unknown Date')
        
        version_data = content.get('version', {})
        last_updated_at = version_data.get('when', 'Unknown Date')
        version_number = version_data.get('number')
        
        print(f"\n   [{ctype.upper()}] (ID: {content_id})")
        print(f"     - title: {title}")
        print(f"     - created_at: {created_at}")
        print(f"     - last_updated_at: {last_updated_at}")
        print(f"     - url: {url_suffix}")
        print(f"     - version: {version_number}")
        print(f"     - status: {status}")
        
        if content_id:
            try:
                mentions, jira_keys = await process_content_body(confluence, content_id)
                print(f"     - Mentions (Extracted): {len(mentions)} found -> {mentions}")
                print(f"     - Jira Links (Extracted): {len(jira_keys)} found -> {jira_keys}")
                all_mentioned_account_ids.update(mentions)

                # Fetch and Process Comments
                comments = await get_comments(confluence, content_id)
                if comments:
                    print(f"     - Comments: {len(comments)} found")
                    for comment in comments:
                        comment_id = comment.get('id')
                        comment_body = comment.get('body', {}).get('storage', {}).get('value', '')
                        comment_history = comment.get('history', {})
                        commenter_account_id = comment_history.get('createdBy', {}).get('accountId')
                        
                        comment_mentions, comment_jira_keys = parse_body_for_relations(comment_body)
                        all_mentioned_account_ids.update(comment_mentions)
                        
                        if commenter_account_id:
                            all_mentioned_account_ids.add(commenter_account_id)
                        
                        print(f"\n       [COMMENT] (ID: {comment_id})")
                        print(f"         - Author Account ID: {commenter_account_id}")
                        print(f"         - Mentions (Extracted): {len(comment_mentions)} found -> {comment_mentions}")
                        print(f"         - Jira Links (Extracted): {len(comment_jira_keys)} found -> {comment_jira_keys}")
                        print(f"         - ActivitySignal Details: (Will use COMMENTED_ON relation)")
                        print(f"           Person {commenter_account_id} -[COMMENTED_ON]-> {ctype.capitalize()} {content_id}")
                        
                        # In the real producer, we wouldn't usually emit a full node for a comment unless we want comments
                        # to be first-class citizens in the graph. Instead, we typically emit a COMMENTED_ON 
                        # relation from the Person to the Page, sometimes storing the comment ID as a property on the relation.
            except Exception as e:
                print(f"     ❌ Failed to fetch/parse body or comments: {e}")


    # 4. Fetch User Details and Build Person Signals
    print(f"\n4. Fetching Identity Details for {len(all_mentioned_account_ids)} Mentions and Commenters...")
    for account_id in all_mentioned_account_ids:
        if not account_id:
            continue
        user_data = await get_user_details_async(confluence, account_id)
        if user_data:
            signal = build_person_signal(user_data, account_id, url)
            print(f"\n   [PERSON SIGNAL] (Account ID: {account_id})")
            print(f"     - source: {signal.source}")
            print(f"     - wba_id: {signal.source}::{signal.attributes.entity_type}::{signal.id}")
            print(f"     - full_name: {signal.attributes.full_name}")
            print(f"     - email: {signal.attributes.email}")

if __name__ == "__main__":
    asyncio.run(main_async())
