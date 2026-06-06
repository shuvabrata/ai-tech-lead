import argparse
from collections import Counter
from typing import Any, Dict, List

from atlassian import Confluence

from common.logger import logger


def fetch_page_comments(confluence: Confluence, page_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    """Fetch all comments for a page/blogpost, paginating through the full result set."""
    logger.debug("Fetching comments for %s content_id=%s", content_type, page_id)
    all_results: List[Dict[str, Any]] = []
    start = 0
    page_size = 50

    try:
        while True:
            response = confluence.get_page_comments(
                page_id,
                expand='body.storage,history',
                start=start,
                limit=page_size,
            )
            results = response.get('results', [])
            if not results:
                break
            all_results.extend(results)
            logger.debug(
                "Fetched %d comments (batch start=%d) for %s content_id=%s",
                len(results),
                start,
                content_type,
                page_id,
            )
            start += len(results)
            # Stop if we received fewer than a full page — no more results.
            if len(results) < page_size:
                break
    except Exception as exc:
        logger.warning(
            "Failed to fetch comments for %s content_id=%s: %s",
            content_type,
            page_id,
            exc,
        )

    logger.debug(
        "Total %d comments fetched for %s content_id=%s",
        len(all_results),
        content_type,
        page_id,
    )
    return all_results


def _summarise_comments_by_author(comments: List[Dict[str, Any]]) -> None:
    """Print a breakdown of comment counts per author."""
    author_counter: Counter = Counter()
    for comment in comments:
        history = comment.get("history", {})
        created_by = history.get("createdBy", {})
        display_name = created_by.get("displayName") or created_by.get("email") or created_by.get("accountId", "unknown")
        author_counter[display_name] += 1

    print(f"\nTotal comments fetched : {len(comments)}")
    print(f"Unique authors         : {len(author_counter)}")
    print("\nComments per author (descending):")
    print(f"{'Author':<50}  {'Count':>6}")
    print("-" * 58)
    for author, count in author_counter.most_common():
        print(f"{author:<50}  {count:>6}")


def main() -> None:
    """Troubleshooting entry point: fetch page comments and summarise by author."""
    parser = argparse.ArgumentParser(
        description="Fetch Confluence page comments and show a per-author breakdown."
    )
    parser.add_argument(
        "page_id",
        help="Confluence page ID to inspect",
    )
    args = parser.parse_args()

    # Load credentials from .config.json sitting next to this file.
    from connectors.producers.confluence.confluence_config import (  # pylint: disable=import-outside-toplevel
        create_confluence_connection,
        load_config_from_file,
    )

    config = load_config_from_file()
    confluence = create_confluence_connection(config)

    print(f"\nFetching comments for page_id={args.page_id} …")
    comments = fetch_page_comments(confluence, args.page_id)
    _summarise_comments_by_author(comments)


if __name__ == "__main__":
    main()
