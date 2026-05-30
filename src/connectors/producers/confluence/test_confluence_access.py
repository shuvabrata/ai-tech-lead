import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set, Tuple

# Add src to python path for model imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from common.activity_signal.models import ActivitySignal, PersonAttributes, Relationship, RelationshipTarget

try:
    from atlassian import Confluence
    import requests
except ImportError:
    print("Error: 'atlassian-python-api' or 'requests' is not installed.")
    print("Please run: pip install atlassian-python-api requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: 'beautifulsoup4' is not installed.")
    print("Please run: pip install beautifulsoup4 lxml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Sync Fetching Functions (To be moved to fetch_confluence.py in Phase 3)
# ---------------------------------------------------------------------------

def fetch_spaces(confluence: Confluence, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch spaces from Confluence."""
    print(f"  [Network] Fetching spaces (limit={limit})...")
    # In a real producer, we'd handle pagination for all spaces
    spaces_response = confluence.get_all_spaces(start=0, limit=limit)
    return spaces_response.get('results', [])

def fetch_cql_results(confluence: Confluence, cql: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch results using Confluence Query Language (CQL)."""
    print(f"  [Network] Executing CQL: {cql}")
    # Expand version and history to get created_at and last_updated_at attributes
    response = confluence.cql(cql, limit=limit, expand="content.version,content.history")
    return response.get('results', [])

def fetch_page_body(confluence: Confluence, page_id: str) -> str:
    """Fetch the storage format body of a page/blogpost."""
    print(f"  [Network] Fetching body for page ID: {page_id}")
    page = confluence.get_page_by_id(page_id, expand='body.storage')
    return page.get('body', {}).get('storage', {}).get('value', '')

def fetch_page_comments(confluence: Confluence, page_id: str) -> List[Dict[str, Any]]:
    """Fetch comments for a page/blogpost."""
    print(f"  [Network] Fetching comments for page ID: {page_id}")
    try:
        response = confluence.get_page_comments(page_id, expand='body.storage,history')
        return response.get('results', [])
    except Exception as e:
        print(f"    ❌ Failed to fetch comments: {e}")
        return []

def parse_body_for_relations(html_body: str) -> Tuple[Set[str], Set[str]]:
    """Parse Confluence storage HTML to extract mentions and Jira links.
    
    Returns:
        A tuple of (set_of_account_ids, set_of_jira_keys)
    """
    if not html_body:
        return set(), set()
        
    soup = BeautifulSoup(html_body, "lxml")
    
    # Extract @mentions: <ri:user ri:account-id="..."/>
    mentions = set()
    for user_tag in soup.find_all("ri:user"):
        account_id = user_tag.get("ri:account-id")
        if account_id:
            mentions.add(account_id)
            
    # Extract Jira Macros
    # <ac:structured-macro ac:name="jira"> ... <ac:parameter ac:name="key">WBA-123</ac:parameter> ...
    jira_keys = set()
    for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
        key_param = macro.find("ac:parameter", {"ac:name": "key"})
        if key_param and key_param.text:
            jira_keys.add(key_param.text)
            
    return mentions, jira_keys

def fetch_user_details(confluence: Confluence, account_id: str) -> Dict[str, Any]:
    """Fetch user details from Confluence REST API."""
    print(f"  [Network] Fetching user details for account: {account_id}")
    try:
        # confluence.url already includes '/wiki' depending on how it's initialized,
        # but the confluence object has a get method we can use that handles paths correctly
        response = confluence.get(f"/rest/api/user?accountId={account_id}")
        return response
    except Exception as e:
        print(f"    ❌ Failed to fetch user details: {e}")
        return {}

# ---------------------------------------------------------------------------
# Async Wrappers
# ---------------------------------------------------------------------------

async def get_spaces(confluence: Confluence, limit: int = 50) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_spaces, confluence, limit)

async def get_recent_content(confluence: Confluence, since_date: datetime, limit: int = 10) -> List[Dict[str, Any]]:
    # Format date for CQL: YYYY-MM-DD
    date_str = since_date.strftime("%Y-%m-%d")
    cql = f'(type=page OR type=blogpost) AND lastModified >= "{date_str}" ORDER BY lastModified DESC'
    return await asyncio.to_thread(fetch_cql_results, confluence, cql, limit)

async def process_content_body(confluence: Confluence, content_id: str) -> Tuple[Set[str], Set[str]]:
    body = await asyncio.to_thread(fetch_page_body, confluence, content_id)
    return await asyncio.to_thread(parse_body_for_relations, body)

async def get_comments(confluence: Confluence, content_id: str) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_page_comments, confluence, content_id)

async def get_user_details(confluence: Confluence, account_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(fetch_user_details, confluence, account_id)

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
    spaces = await get_spaces(confluence, limit=5)
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
    
    recent_items = await get_recent_content(confluence, lookback, limit=5)
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
        user_data = await get_user_details(confluence, account_id)
        if user_data:
            signal = build_person_signal(user_data, account_id, url)
            print(f"\n   [PERSON SIGNAL] (Account ID: {account_id})")
            print(f"     - source: {signal.source}")
            print(f"     - wba_id: {signal.source}::{signal.attributes.entity_type}::{signal.id}")
            print(f"     - full_name: {signal.attributes.full_name}")
            print(f"     - email: {signal.attributes.email}")

if __name__ == "__main__":
    asyncio.run(main_async())
