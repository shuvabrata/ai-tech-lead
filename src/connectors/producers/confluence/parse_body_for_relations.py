from typing import Set, Tuple
from bs4 import BeautifulSoup

def parse_body_for_relations(html_body: str) -> Tuple[Set[str], Set[str]]:
    """Parse Confluence storage HTML to extract mentions and Jira links.
    Returns:
        A tuple of (set_of_account_ids, set_of_jira_keys)
    """
    if not html_body:
        return set(), set()
    soup = BeautifulSoup(html_body, "lxml")
    mentions = set()
    for user_tag in soup.find_all("ri:user"):
        account_id = user_tag.get("ri:account-id")
        if account_id:
            mentions.add(account_id)
    jira_keys = set()
    for macro in soup.find_all("ac:structured-macro", {"ac:name": "jira"}):
        key_param = macro.find("ac:parameter", {"ac:name": "key"})
        if key_param and key_param.text:
            jira_keys.add(key_param.text)
    return mentions, jira_keys
