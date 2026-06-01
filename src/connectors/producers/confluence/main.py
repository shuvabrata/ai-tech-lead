"""Confluence ActivitySignal producer.

This module converts the prep workflow in ``test_confluence_access.py`` into a
real producer entrypoint.  It reuses the existing fetch helpers wherever
possible and publishes normalized ``ActivitySignal`` payloads to RabbitMQ.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from atlassian import Confluence  # type: ignore[import-untyped]

from common.activity_signal.models import (
    ActivitySignal,
    BlogpostAttributes,
    PageAttributes,
    PersonAttributes,
    Relationship,
    RelationshipTarget,
    SpaceAttributes,
)
from common.logger import logger
from common.messaging.rabbitmq import RabbitMQPublisher
from connectors.producers.confluence.confluence_config import (
    create_confluence_connection,
    load_config_from_file,
    load_config_from_server,
)
from connectors.producers.confluence.confluence_settings import (
    get_lookback_days,
    get_max_results_per_page,
)
from connectors.producers.confluence.confluence_helpers import (
    get_comments,
    get_recent_content,
    get_likes,
    get_spaces,
    get_user_details_async,
)
from connectors.producers.confluence.fetch_page_body import fetch_page_body
from connectors.producers.confluence.parse_body_for_relations import (
    parse_body_for_relations,
)
from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor

_SOURCE = "confluence"
_VERSION = "1.0"


def _connector_url() -> str:
    api_server = os.environ.get("API_SERVER", "http://localhost:8000")
    return f"{api_server.rstrip('/')}/connectors/confluence"


def _normalize_space_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    return value.upper() if value else None


def _first_string(data: Dict[str, Any], paths: Sequence[Sequence[str]]) -> Optional[str]:
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
            if current is None:
                break
        if isinstance(current, str) and current.strip():
            return current.strip()
    return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _content_url(base_url: str, content: Dict[str, Any]) -> Optional[str]:
    links = content.get("_links")
    if isinstance(links, dict):
        webui = links.get("webui")
        if isinstance(webui, str) and webui.strip():
            if webui.startswith("http://") or webui.startswith("https://"):
                return webui
            return f"{base_url.rstrip('/')}/{webui.lstrip('/')}"
    return None


def _space_url(base_url: str, space: Dict[str, Any]) -> Optional[str]:
    links = space.get("_links")
    if isinstance(links, dict):
        webui = links.get("webui")
        if isinstance(webui, str) and webui.strip():
            if webui.startswith("http://") or webui.startswith("https://"):
                return webui
            return f"{base_url.rstrip('/')}/{webui.lstrip('/')}"
    return None


def _content_type(content: Dict[str, Any]) -> str:
    return (content.get("type") or "page").lower()


def _content_entity_type(content: Dict[str, Any]) -> str:
    return "Blogpost" if _content_type(content) == "blogpost" else "Page"


def _content_id(content: Dict[str, Any]) -> Optional[str]:
    raw = content.get("id")
    return str(raw) if raw is not None and str(raw).strip() else None


def _content_title(content: Dict[str, Any]) -> Optional[str]:
    raw = content.get("title")
    return str(raw) if raw is not None and str(raw).strip() else None


def _content_created_at(content: Dict[str, Any]) -> str:
    return (
        _first_string(content, [("history", "createdDate"), ("createdAt",), ("version", "createdAt")])
        or datetime.now(timezone.utc).isoformat()
    )


def _content_last_updated_at(content: Dict[str, Any]) -> str:
    return (
        _first_string(content, [("version", "when"), ("updatedAt",), ("version", "createdAt")])
        or _content_created_at(content)
    )


def _content_version(content: Dict[str, Any]) -> Optional[int]:
    version = content.get("version")
    if isinstance(version, dict):
        number = version.get("number")
        if isinstance(number, int):
            return number
        if isinstance(number, str):
            try:
                return int(number)
            except ValueError:
                return None
    return None


def _content_event_time(content: Dict[str, Any]) -> datetime:
    candidates = [
        _first_string(content, [("version", "when")]),
        _first_string(content, [("history", "createdDate")]),
        _first_string(content, [("updatedAt",)]),
    ]
    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed
    return datetime.now(timezone.utc)


def _space_event_time(space: Dict[str, Any]) -> datetime:
    candidates = [
        _first_string(space, [("updatedAt",)]),
        _first_string(space, [("lastModificationDate",)]),
        _first_string(space, [("createdAt",)]),
        _first_string(space, [("creationDate",)]),
    ]
    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed
    return datetime.now(timezone.utc)


def _space_key_from_content(content: Dict[str, Any]) -> Optional[str]:
    direct = _first_string(content, [("space", "key")])
    if direct:
        return _normalize_space_key(direct)
    space_key = _first_string(content, [("spaceKey",)])
    if space_key:
        return _normalize_space_key(space_key)
    return None


def _parent_page_id(content: Dict[str, Any]) -> Optional[str]:
    parent_id = _first_string(content, [("parentId",)])
    if parent_id:
        return parent_id
    ancestors = content.get("ancestors")
    if isinstance(ancestors, list) and ancestors:
        last = ancestors[-1]
        if isinstance(last, dict):
            ancestor_id = _first_string(last, [("id",)])
            if ancestor_id:
                return ancestor_id
    return None


def _comment_body(comment: Dict[str, Any]) -> str:
    body = comment.get("body")
    if isinstance(body, dict):
        storage = body.get("storage")
        if isinstance(storage, dict):
            value = storage.get("value")
            if isinstance(value, str):
                return value
    return ""


def _comment_status(comment: Dict[str, Any]) -> str:
    resolution_status = _first_string(comment, [("resolutionStatus",)])
    if not resolution_status:
        return "open"
    normalized = resolution_status.lower()
    if normalized in {"resolved", "closed"}:
        return normalized
    return "open"


def _comment_timestamp(comment: Dict[str, Any]) -> datetime:
    candidates = [
        _first_string(comment, [("version", "when")]),
        _first_string(comment, [("history", "createdDate")]),
        _first_string(comment, [("createdAt",)]),
    ]
    for candidate in candidates:
        parsed = _parse_datetime(candidate)
        if parsed:
            return parsed
    return datetime.now(timezone.utc)


def _relationship_key(rel: Relationship) -> Tuple[Any, ...]:
    props = tuple(sorted((rel.properties or {}).items()))
    target = rel.target
    return (
        rel.type,
        rel.direction,
        target.source,
        target.entity_type,
        target.id,
        target.email,
        target.url,
        props,
    )


def _dedupe_relationships(relationships: Iterable[Relationship]) -> List[Relationship]:
    seen: Set[Tuple[Any, ...]] = set()
    result: List[Relationship] = []
    for rel in relationships:
        key = _relationship_key(rel)
        if key in seen:
            continue
        seen.add(key)
        result.append(rel)
    return result


def _person_target(
    account_id: str,
    email: Optional[str] = None,
) -> RelationshipTarget:
    return RelationshipTarget(
        source=_SOURCE,
        entity_type="Person",
        id=account_id,
        email=email,
    )


def _content_target(entity_type: str, entity_id: str) -> RelationshipTarget:
    return RelationshipTarget(
        source=_SOURCE,
        entity_type=entity_type,
        id=entity_id,
    )


def build_person_signal(
    user_data: Dict[str, Any],
    account_id: str,
    confluence_url: str,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a person referenced by Confluence."""
    email = user_data.get("email")
    public_name = user_data.get("publicName")
    display_name = user_data.get("displayName")
    full_name = public_name or display_name or account_id

    try:
        attrs = PersonAttributes(
            full_name=full_name,
            account_id=account_id,
            email=email if isinstance(email, str) and email.strip() else None,
        )
        return ActivitySignal(
            source=_SOURCE,
            id=account_id,
            source_config=confluence_url,
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Skipping Person signal for '%s' (validation error): %s", account_id, exc)
        return None


def build_space_signal(space: Dict[str, Any], confluence_url: str) -> Optional[ActivitySignal]:
    key = _normalize_space_key(space.get("key"))
    name = space.get("name")
    if not key or not isinstance(name, str) or not name.strip():
        return None

    attrs = SpaceAttributes(
        key=key,
        name=name,
        type=space.get("type"),
        url=_space_url(confluence_url, space),
    )
    return ActivitySignal(
        source=_SOURCE,
        id=key,
        source_config=confluence_url,
        connector_url=_connector_url(),
        event_time=_space_event_time(space),
        version=_VERSION,
        attributes=attrs,
    )


def build_content_signal(
    content: Dict[str, Any],
    confluence_url: str,
    relationships: List[Relationship],
) -> Optional[ActivitySignal]:
    content_id = _content_id(content)
    title = _content_title(content)
    if not content_id or not title:
        return None

    event_time = _content_event_time(content)
    content_type = _content_type(content)
    common_kwargs: Dict[str, Any] = {
        "title": title,
        "created_at": _content_created_at(content),
        "last_updated_at": _content_last_updated_at(content),
        "url": _content_url(confluence_url, content),
        "version": _content_version(content),
        "status": content.get("status") if isinstance(content.get("status"), str) else None,
    }

    if content_type == "blogpost":
        attrs = BlogpostAttributes(**common_kwargs)
    else:
        attrs = PageAttributes(**common_kwargs)

    return ActivitySignal(
        source=_SOURCE,
        id=content_id,
        source_config=confluence_url,
        connector_url=_connector_url(),
        event_time=event_time,
        version=_VERSION,
        attributes=attrs,
        relationships=relationships,
    )


def _extract_relationships_and_people(
    content: Dict[str, Any],
    comments: List[Dict[str, Any]],
    body_html: str,
    body_mentions: Optional[Set[str]] = None,
    body_jira_keys: Optional[Set[str]] = None,
) -> Tuple[List[Relationship], Set[str]]:
    relationships: List[Relationship] = []
    people: Set[str] = set()

    if body_mentions is None or body_jira_keys is None:
        body_mentions, body_jira_keys = parse_body_for_relations(body_html)
    else:
        body_mentions = set(body_mentions)
        body_jira_keys = set(body_jira_keys)

    people.update(body_mentions)
    for account_id in sorted(body_mentions):
        relationships.append(
            Relationship(
                type="MENTIONS",
                target=_person_target(account_id),
            )
        )
    for jira_key in sorted(body_jira_keys):
        relationships.append(
            Relationship(
                type="REFERENCES",
                target=RelationshipTarget(source="jira", entity_type="Issue", id=jira_key),
            )
        )

    created_by = _first_string(
        content,
        [
            ("history", "createdBy", "accountId"),
            ("history", "createdBy", "id"),
        ],
    )
    if created_by:
        people.add(created_by)
        relationships.append(
            Relationship(
                type="CREATED",
                direction="IN",
                target=_person_target(created_by),
                properties={"timestamp": _content_event_time(content).isoformat()},
            )
        )

    modified_by = _first_string(
        content,
        [
            ("version", "by", "accountId"),
            ("history", "lastUpdated", "accountId"),
        ],
    )
    if modified_by:
        people.add(modified_by)
        relationships.append(
            Relationship(
                type="MODIFIED",
                direction="IN",
                target=_person_target(modified_by),
                properties={"timestamp": _content_event_time(content).isoformat()},
            )
        )

    space_key = _space_key_from_content(content)
    if space_key:
        relationships.append(
            Relationship(
                type="IN_SPACE",
                target=_content_target("Space", space_key),
            )
        )

    parent_id = _parent_page_id(content)
    if parent_id and _content_type(content) == "page":
        relationships.append(
            Relationship(
                type="CHILD_OF",
                target=_content_target("Page", parent_id),
            )
        )

    for comment in comments:
        comment_author = _first_string(
            comment,
            [
                ("history", "createdBy", "accountId"),
                ("history", "createdBy", "id"),
                ("authorId",),
            ],
        )
        if not comment_author:
            continue

        people.add(comment_author)
        comment_body = _comment_body(comment)
        comment_mentions, comment_jira_keys = parse_body_for_relations(comment_body)
        people.update(comment_mentions)

        relationships.append(
            Relationship(
                type="COMMENTED_ON",
                direction="IN",
                target=_person_target(comment_author),
                properties={
                    "timestamp": _comment_timestamp(comment).isoformat(),
                    "status": _comment_status(comment),
                },
            )
        )

        for account_id in sorted(comment_mentions):
            relationships.append(
                Relationship(
                    type="MENTIONS",
                    target=_person_target(account_id),
                )
            )
        for jira_key in sorted(comment_jira_keys):
            relationships.append(
                Relationship(
                    type="REFERENCES",
                    target=RelationshipTarget(source="jira", entity_type="Issue", id=jira_key),
                )
            )

    return _dedupe_relationships(relationships), people


def _extract_reaction_relationships(
    content: Dict[str, Any],
    likes: List[Dict[str, Any]],
) -> Tuple[List[Relationship], Set[str]]:
    relationships: List[Relationship] = []
    people: Set[str] = set()

    for like in likes:
        account_id = _first_string(like, [("accountId",), ("account_id",), ("id",)])
        if not account_id:
            continue
        people.add(account_id)
        relationships.append(
            Relationship(
                type="REACTED_TO",
                direction="IN",
                target=_person_target(account_id),
            )
        )

    return _dedupe_relationships(relationships), people


async def _publish_person_signals(
    publisher: RabbitMQPublisher,
    confluence: Confluence,
    account_ids: Iterable[str],
    confluence_url: str,
) -> int:
    published = 0
    unique_account_ids = [account_id for account_id in sorted(set(account_ids)) if account_id]
    if not unique_account_ids:
        return 0

    user_datas = await asyncio.gather(
        *(get_user_details_async(confluence, account_id) for account_id in unique_account_ids)
    )
    for account_id, user_data in zip(unique_account_ids, user_datas):
        if not user_data:
            continue
        signal = build_person_signal(user_data, account_id, confluence_url)
        if signal is None:
            continue
        logger.debug(
            "Publishing Person signal: id=%s relationships=%d",
            account_id,
            len(signal.relationships) if hasattr(signal, 'relationships') else 0,
        )
        await publisher.publish(signal)
        published += 1
    return published


async def _publish_content_signal(
    publisher: RabbitMQPublisher,
    confluence: Confluence,
    content: Dict[str, Any],
    confluence_url: str,
    account_ids: Set[str],
) -> int:
    content_id = _content_id(content)
    if not content_id:
        return 0

    body_value = await asyncio.to_thread(fetch_page_body, confluence, content_id)
    body_mentions, body_jira_keys = parse_body_for_relations(body_value)
    comments = await get_comments(confluence, content_id, _content_type(content))
    likes = await get_likes(confluence, content_id, _content_type(content))
    relationships, people = _extract_relationships_and_people(
        content,
        comments,
        body_value,
        body_mentions,
        body_jira_keys,
    )
    account_ids.update(people)

    reaction_relationships, reaction_people = _extract_reaction_relationships(content, likes)
    account_ids.update(reaction_people)
    relationships.extend(reaction_relationships)
    relationships = _dedupe_relationships(relationships)

    signal = build_content_signal(content, confluence_url, relationships)
    if signal is None:
        return 0
    logger.debug(
        "Publishing %s signal: id=%s relationships=%d",
        signal.entity_type,
        signal.id,
        len(signal.relationships) if hasattr(signal, 'relationships') else 0,
    )
    await publisher.publish(signal)
    return 1


async def process_account(
    publisher: RabbitMQPublisher,
    confluence: Confluence,
    account: Dict[str, Any],
) -> int:
    """Process one Confluence config record and publish all signals."""
    confluence_url = account["url"]
    sync_resource_id = str(account.get("id") or confluence_url)
    include_spaces = account.get("include_spaces", []) or []
    exclude_spaces = account.get("exclude_spaces", []) or []

    last_synced_at = await get_sync_cursor(_SOURCE, sync_resource_id)
    lookback_days = get_lookback_days()
    max_results_per_page = get_max_results_per_page()
    since_date = last_synced_at or (datetime.now(timezone.utc) - timedelta(days=lookback_days))

    logger.info(
        "Processing Confluence config id=%s url=%s last_synced_at=%s",
        sync_resource_id,
        confluence_url,
        last_synced_at,
    )

    total_published = 0
    entity_type_counts = {"Page": 0, "Blogpost": 0, "Person": 0, "Space": 0}
    account_ids: Set[str] = set()
    include_space_keys = {
        _normalize_space_key(space) for space in include_spaces if _normalize_space_key(space)
    }
    exclude_space_keys = {
        _normalize_space_key(space) for space in exclude_spaces if _normalize_space_key(space)
    }

    spaces = await get_spaces(confluence)
    for space in spaces:
        key = _normalize_space_key(space.get("key"))
        if include_space_keys and key not in include_space_keys:
            continue
        if key in exclude_space_keys:
            continue

        signal = build_space_signal(space, confluence_url)
        if signal is None:
            continue
        logger.debug(
            "Publishing Space signal: id=%s relationships=%d",
            key,
            len(signal.relationships) if hasattr(signal, 'relationships') else 0,
        )
        await publisher.publish(signal)
        total_published += 1
        entity_type_counts["Space"] += 1

    recent_items = await get_recent_content(
        confluence,
        since_date,
        limit=max_results_per_page,
        include_spaces=include_spaces,
        exclude_spaces=exclude_spaces,
    )
    logger.info("Fetched %d recently changed content items", len(recent_items))

    for item in recent_items:
        content = item.get("content", item)
        if not isinstance(content, dict):
            continue
        # Determine entity type for count
        entity_type = _content_entity_type(content)
        published_count = await _publish_content_signal(
            publisher,
            confluence,
            content,
            confluence_url,
            account_ids,
        )
        total_published += published_count
        if entity_type in entity_type_counts:
            entity_type_counts[entity_type] += published_count

    person_published = await _publish_person_signals(
        publisher,
        confluence,
        account_ids,
        confluence_url,
    )
    total_published += person_published
    entity_type_counts["Person"] += person_published

    await set_sync_cursor(_SOURCE, sync_resource_id, datetime.now(timezone.utc))
    logger.info(
        "Published counts: Pages=%d, Blogposts=%d, Spaces=%d, People=%d",
        entity_type_counts["Page"],
        entity_type_counts["Blogpost"],
        entity_type_counts["Space"],
        entity_type_counts["Person"],
    )
    return total_published


async def main_async() -> None:
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()

    logger.info("Confluence ActivitySignal Producer starting (config_source=%s)", config_source)
    if config_source == "SERVER":
        config = load_config_from_server()
    else:
        config = load_config_from_file()

    accounts = config.get("account", [])
    if not accounts:
        logger.warning("No Confluence accounts configured - exiting.")
        return

    async with RabbitMQPublisher(rabbitmq_url) as publisher:
        for account in accounts:
            if not account.get("enabled", True):
                logger.info("Skipping disabled Confluence config id=%s", account.get("id"))
                continue

            if not account.get("url") or not account.get("email") or not account.get("api_token"):
                logger.warning(
                    "Skipping Confluence config id=%s due to missing url/email/api_token",
                    account.get("id"),
                )
                continue

            confluence = create_confluence_connection({"account": [account]})
            try:
                published = await process_account(publisher, confluence, account)
                logger.info(
                    "Finished Confluence config id=%s url=%s published=%d",
                    account.get("id"),
                    account.get("url"),
                    published,
                )
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "Failed to process Confluence config id=%s url=%s: %s",
                    account.get("id"),
                    account.get("url"),
                    exc,
                    exc_info=True,
                )

    logger.info("Confluence ActivitySignal Producer finished.")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
