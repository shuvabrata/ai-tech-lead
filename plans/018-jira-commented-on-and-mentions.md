# Plan 018: Jira COMMENTED_ON and MENTIONS relationships

> **Status**: Phase 1 COMPLETE — implementation in progress. Design decisions resolved via grill-me session on 2026-08-21.

## Status

- **Phase 1 (Fetch + Map)**: ✅ COMPLETE 2026-08-23 — 21 new unit tests pass; full Jira unit suite (28) green.

- **Priority**: P1 (feature parity — GitHub Issues/PRs and Confluence Pages/Blogposts already have these relationships)
- **Effort**: L (touches fetch, map, producer, consumer, collaboration, catalog, docs, tests)
- **Risk**: MEDIUM (JQL change affects incremental sync behavior; ADF parsing is new code)
- **Depends on**: none
- **Category**: feature / data completeness
- **Planned at**: 2026-08-21

## Why this matters

Jira Initiatives, Epics, and Issues currently have **no** `COMMENTED_ON` or `MENTIONS` relationships. This means:

- **Collaboration scores are incomplete** — comment-based collaboration layers only cover GitHub Issues/PRs and Confluence, missing all Jira comment activity.
- **Catalog queries are blind** — no Jira queries surface comment participants or @mentioned people.
- **AI agent can't answer** — the Neo4j prompt doesn't list these relationships for Jira entities, so the LLM can't generate queries about Jira comments.

GitHub Issues, GitHub PRs, Confluence Pages, and Confluence Blogposts all have full `COMMENTED_ON` + `MENTIONS` support. This plan brings Jira to parity.

## Design decisions (resolved)

| # | Decision | Answer |
|---|---|---|
| 1 | Scope — which Jira entities? | Initiatives, Epics, and Issues |
| 2 | MENTIONS extraction | Parse ADF JSON from `description` + all comment bodies; verbose debug logging |
| 3 | COMMENTED_ON direction | `"IN"` — matches GitHub/Confluence convention; stored as `(Person)-[:COMMENTED_ON]->(Entity)` |
| 4 | Comment fetch strategy | Per-entity API call (`GET /rest/api/3/issue/{id}/comment`); configurable via `JIRA_FETCH_COMMENTS` env var (default `true`) |
| 5 | Incremental sync | Switch JQL from `created >=` to `updated >=` when `last_synced_at` cursor exists |
| 6 | Consumer snapshot pattern | Apply `replace_snapshot_interaction_relationships` to `merge_initiative` + `merge_epic` (copy from `merge_issue`) |
| 7 | Collaboration layers | 5 new layers: `jira_issue_comment_engagement` (3.0), `jira_issue_co_commenters` (2.0), `jira_epic_initiative_comment_engagement` (2.0), `jira_epic_initiative_co_commenters` (1.0), `jira_mentions` (2.0) |
| 8 | Catalog queries | 4 new + 1 updated (`team_knowledge_surface_area`) |
| 9 | MENTIONS direction | `None` (undirected, entity→Person via `accountId`) |
| 10 | Person signals | Full for commenters (user object from API), minimal stub for @mentioned users (accountId only) |
| 11 | Processing model | One entity at a time: fetch comments → parse mentions → emit Person signals → build signal → publish |
| 12 | Tests | Unit: fetch/map/build/consumer; Integration: manual |
| 13 | Prompt update | `neo4j_prompt.md` — add `COMMENTED_ON`/`MENTIONS` to Work Items section |
| 14 | Phasing | 6 sequential phases (see below) |

---

## Phase 1: Fetch + Map layer  ✅ COMPLETE (2026-08-23)

**Goal**: Add comment fetching and ADF mention extraction. Switch JQL to `updated >=` for incremental sync. No signal shape changes yet.

### Files to create

| File | Purpose |
|---|---|
| `tests/producers/jira/__init__.py` | Package init |
| `tests/producers/jira/test_fetch_jira_comments.py` | Unit tests for comment fetching |
| `tests/producers/jira/test_map_jira_mentions.py` | Unit tests for ADF mention extraction |

### Files to modify

| File | Changes |
|---|---|
| `src/connectors/producers/jira/fetch_jira.py` | Add `fetch_comments(jira, issue_id_or_key)` function; add `resolve_jql_date_field(last_synced_at)` helper; update `fetch_initiatives`, `fetch_epics`, `fetch_issues` to accept optional `last_synced_at` and use `updated >=` when present |
| `src/connectors/producers/jira/map_jira.py` | Add `extract_mentions_from_adf(adf_doc)` function that recursively walks ADF JSON, finds `{"type": "mention"}` nodes, extracts `attrs.id` (accountId), deduplicates, and returns list of accountIds; add `extract_mentions_from_texts(*texts)` helper that combines description + comment bodies |

### Detailed changes

#### `fetch_jira.py`

```python
# New function
def fetch_comments(
    jira: Any,
    issue_id_or_key: str,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch all comments for a Jira issue.

    Uses cursor-based pagination via the startAt parameter.

    Returns:
        List of raw comment dicts, each with keys: id, author (user object
        with accountId/displayName/emailAddress), body (ADF JSON), created,
        updated.
    """

# New helper
def resolve_jql_date_field(last_synced_at: Optional[datetime]) -> tuple[str, str]:
    """Return (field_name, date_string) for JQL filtering.

    When last_synced_at is None (first run), uses 'created' with the lookback
    cutoff. When a cursor exists (incremental run), uses 'updated' with the
    cursor timestamp so that entities with new comments are re-fetched.
    """

# Modified signatures
def fetch_initiatives(
    jira: Any,
    lookback_days: int = 90,
    max_results_per_page: int = 100,
    last_synced_at: Optional[datetime] = None,  # NEW
) -> List[Dict[str, Any]]:

def fetch_epics(
    jira: Any,
    lookback_days: int = 90,
    max_results_per_page: int = 100,
    last_synced_at: Optional[datetime] = None,  # NEW
) -> List[Dict[str, Any]]:

def fetch_issues(
    jira: Any,
    lookback_days: int = 90,
    max_results_per_page: int = 100,
    last_synced_at: Optional[datetime] = None,  # NEW
) -> List[Dict[str, Any]]:
```

JQL change (applies to all three fetch functions):
```python
# Before (current):
jql = f"issuetype = Epic AND created >= {cutoff_date_str} ORDER BY created DESC"

# After:
date_field, date_str = resolve_jql_date_field(lookback_days, last_synced_at)
jql = f"issuetype = Epic AND {date_field} >= {date_str} ORDER BY created DESC"
```

#### `map_jira.py`

```python
def extract_mentions_from_adf(adf_doc: Optional[Dict[str, Any]]) -> List[str]:
    """Recursively walk an ADF document and extract @mention accountIds.

    ADF mention nodes look like:
        {"type": "mention", "attrs": {"id": "accountId:abc123", ...}}

    Returns deduplicated list of accountId strings (without 'accountId:' prefix
    if present).
    """

def extract_mentions_from_texts(
    description_adf: Optional[Dict[str, Any]],
    comment_bodies: List[Dict[str, Any]],
) -> List[str]:
    """Extract unique @mentioned accountIds from description + comment bodies.

    Skips self-mentions (caller handles filtering by reporter accountId).
    Logs extracted mentions at DEBUG level for troubleshooting Person mapping.
    """
```

### Phase 1 gate (tests must pass before moving to Phase 2)

```bash
pytest -m unit tests/producers/jira/test_fetch_jira_comments.py -v
pytest -m unit tests/producers/jira/test_map_jira_mentions.py -v
```

**Test coverage:**
- `test_fetch_comments_returns_list` — happy path with mock API response
- `test_fetch_comments_empty` — issue with no comments returns `[]`
- `test_fetch_comments_api_error` — API error returns `[]`, logs error
- `test_fetch_comments_pagination` — multiple pages aggregated correctly
- `test_resolve_jql_date_field_first_run` — no cursor → uses `created` + lookback
- `test_resolve_jql_date_field_incremental` — cursor present → uses `updated` + cursor date
- `test_extract_mentions_simple` — single mention in description
- `test_extract_mentions_multiple` — multiple mentions across description + comments
- `test_extract_mentions_dedup` — same person mentioned twice → one entry
- `test_extract_mentions_no_mentions` — text with no mentions → empty list
- `test_extract_mentions_nested_adf` — mentions inside nested ADF structures (paragraphs, lists, tables)
- `test_extract_mentions_strips_accountid_prefix` — `accountId:abc123` → `abc123`

---

## Phase 2: Producer signal building

**Goal**: `build_initiative_signal`, `build_epic_signal`, and `build_issue_signal` accept `comments_data` and `mention_account_ids`. Per-entity processing loop in `publish_signals` fetches comments, parses mentions, emits Person signals, then builds signals.

### Files to create

| File | Purpose |
|---|---|
| `tests/producers/jira/test_build_signals_with_comments.py` | Unit tests for signal building with new relationships |

### Files to modify

| File | Changes |
|---|---|
| `src/connectors/producers/jira/main.py` | Add `comments_data` and `mention_account_ids` params to `build_initiative_signal`, `build_epic_signal`, `build_issue_signal`; add `COMMENTED_ON` (direction="IN", timestamp) and `MENTIONS` (direction=None, accountId) relationship building; add `JIRA_FETCH_COMMENTS` env var check; add per-entity comment fetch + mention parse + Person signal emission in `publish_signals`; pass `last_synced_at` to fetch functions |

### Detailed changes

#### Signal builder additions (all three `build_*_signal` functions)

```python
def build_issue_signal(
    issue_data: Dict[str, Any],
    jira_base_url: str,
    epic_id: Optional[str] = None,
    sprint_ids: Optional[List[str]] = None,
    assignee_person_id: Optional[str] = None,
    reporter_person_id: Optional[str] = None,
    team_id: Optional[str] = None,
    comments_data: Optional[List[Dict[str, Any]]] = None,      # NEW
    mention_account_ids: Optional[List[str]] = None,            # NEW
) -> Optional[ActivitySignal]:
```

New relationship building (inside each builder, before `return ActivitySignal(...)`):

```python
# COMMENTED_ON → each comment (direction="IN", with timestamp property)
if comments_data:
    for comment in comments_data:
        account_id = comment.get("accountId")
        if not account_id:
            continue
        rels.append(
            Relationship(
                type="COMMENTED_ON",
                direction="IN",
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    id=account_id,
                ),
                properties={"timestamp": comment.get("timestamp", "")},
            )
        )

# MENTIONS → each @mentioned accountId (undirected, skip self-refs)
if mention_account_ids:
    reporter_id = ...  # extract from signal context
    for account_id in mention_account_ids:
        if account_id == reporter_id:
            logger.debug("Skipping self-mention: accountId=%s", account_id)
            continue
        rels.append(
            Relationship(
                type="MENTIONS",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    id=account_id,
                ),
            )
        )
```

#### Per-entity processing in `publish_signals`

```python
# New helper
async def _process_entity_with_comments(
    publisher, jira, entity_raw, map_fn, build_fn, jira_base_url,
    seen_persons, fetch_comments_flag, **build_kwargs
):
    """Fetch comments, parse mentions, emit Person signals, build & publish."""
    entity_data = map_fn(entity_raw, jira_base_url)
    entity_key = entity_data["key"]
    jira_issue_id = entity_raw.get("id", "")

    comments_data = []
    mention_account_ids = []

    if fetch_comments_flag and jira_issue_id:
        comments_raw = await asyncio.to_thread(fetch_comments, jira, jira_issue_id)
        logger.debug("Fetched %d comments for %s", len(comments_raw), entity_key)

        for c in comments_raw:
            author = c.get("author") or {}
            account_id = author.get("accountId")
            if not account_id:
                continue
            comments_data.append({
                "accountId": account_id,
                "timestamp": c.get("created", ""),
            })

        # Parse ADF mentions from description + comment bodies
        description_adf = entity_raw.get("fields", {}).get("description")
        comment_bodies_adf = [c.get("body") for c in comments_raw if c.get("body")]
        mention_account_ids = extract_mentions_from_texts(description_adf, comment_bodies_adf)
        logger.debug("Extracted %d mentions from %s: %s", len(mention_account_ids), entity_key, mention_account_ids)

    # Emit Person signals for new commenters and mentioned users
    all_account_ids = set()
    for c in comments_data:
        all_account_ids.add(c["accountId"])
    for m in mention_account_ids:
        all_account_ids.add(m)

    for account_id in all_account_ids:
        if account_id in seen_persons:
            continue
        seen_persons.add(account_id)
        # Build minimal Person signal (commenters get full data if available)
        person_signal = build_person_signal_from_account_id(account_id, comments_data, jira_base_url)
        if person_signal:
            await publisher.publish(person_signal)

    # Build and publish the entity signal
    signal = build_fn(
        entity_data,
        jira_base_url,
        comments_data=comments_data or None,
        mention_account_ids=mention_account_ids or None,
        **build_kwargs,
    )
    if signal:
        await publisher.publish(signal)
```

#### Env var

```python
JIRA_FETCH_COMMENTS = os.getenv("JIRA_FETCH_COMMENTS", "true").lower() in ("true", "1", "yes")
```

### Phase 2 gate

```bash
pytest -m unit tests/producers/jira/test_build_signals_with_comments.py -v
```

**Test coverage:**
- `test_build_issue_signal_with_comments` — COMMENTED_ON edges emitted with direction="IN", timestamp
- `test_build_epic_signal_with_comments` — same for Epics
- `test_build_initiative_signal_with_comments` — same for Initiatives
- `test_build_issue_signal_with_mentions` — MENTIONS edges emitted with direction=None, accountId target
- `test_build_issue_signal_skips_self_mentions` — reporter mentioning themselves → skipped
- `test_build_issue_signal_no_comments` — comments_data=None → no COMMENTED_ON edges
- `test_build_issue_signal_empty_comments` — comments_data=[] → no COMMENTED_ON edges
- `test_build_issue_signal_skips_comment_without_accountid` — comment with missing author → skipped
- `test_build_issue_signal_verbose_logging` — DEBUG log emitted with mention/comment counts
- `test_jira_fetch_comments_disabled` — JIRA_FETCH_COMMENTS=false → no comments fetched, no edges

---

## Phase 3: Consumer — snapshot pattern for merge_initiative and merge_epic

**Goal**: `merge_initiative` and `merge_epic` route `COMMENTED_ON`/`REACTED_TO` through `replace_snapshot_interaction_relationships`, matching `merge_issue` and `merge_pull_request`.

### Files to create

| File | Purpose |
|---|---|
| `tests/test_consumer_jira_comments.py` | Unit tests for consumer snapshot pattern on Initiative/Epic |

### Files to modify

| File | Changes |
|---|---|
| `src/connectors/neo4j_db/models.py` | In `merge_initiative`: replace `for rel in relationships: merge_relationship(session, rel)` with snapshot pattern; same for `merge_epic` |

### Detailed changes

In `merge_initiative` (currently lines ~1345-1350):
```python
# Before:
if relationships:
    for rel in relationships:
        merge_relationship(session, rel)

# After:
if relationships:
    interaction_rels = [r for r in relationships if r.type in ("COMMENTED_ON", "REACTED_TO")]
    other_rels = [r for r in relationships if r.type not in ("COMMENTED_ON", "REACTED_TO")]
    replace_snapshot_interaction_relationships(session, initiative.id, "Initiative", interaction_rels)
    for rel in other_rels:
        merge_relationship(session, rel)
```

Same change in `merge_epic` (currently lines ~1415-1420), using `epic.id` and `"Epic"`.

### Phase 3 gate

```bash
pytest -m unit tests/test_consumer_jira_comments.py -v
```

**Test coverage:**
- `test_merge_initiative_routes_commented_on_to_snapshot` — COMMENTED_ON rels passed to snapshot function
- `test_merge_initiative_other_rels_use_merge_relationship` — non-interaction rels use normal merge
- `test_merge_epic_routes_commented_on_to_snapshot` — same for Epic
- `test_merge_epic_other_rels_use_merge_relationship` — same for Epic
- `test_merge_initiative_no_relationships` — empty relationships list doesn't crash
- `test_snapshot_aggregates_count_and_timestamps` — count, first_interaction_at, last_interaction_at computed correctly
- `test_snapshot_idempotent` — re-processing same signal produces same result

---

## Phase 4: Collaboration network + Catalog queries

**Goal**: Add 5 new collaboration layers and 4 new catalog queries + 1 updated query.

### Files to create

| File | Purpose |
|---|---|
| `queries_catalog/jira/issue_comment_participants.yaml` | People who commented on Jira Issues, grouped by project |
| `queries_catalog/jira/epic_initiative_comment_engagement.yaml` | Epics/Initiatives with most comment activity |
| `queries_catalog/cross_domain/cross_platform_comment_activity.yaml` | Unified view: who comments across Jira + GitHub + Confluence |
| `queries_catalog/jira/mentioned_people_jira.yaml` | People most frequently @mentioned in Jira |

### Files to modify

| File | Changes |
|---|---|
| `src/app/analytics/collaboration/config.py` | Add 5 new layer definitions |
| `src/app/analytics/collaboration/queries/collaboration_score.cypher` | Add 5 new UNION ALL sub-queries |
| `queries_catalog/cross_domain/team_knowledge_surface_area.yaml` | Extend COMMENTED_ON traversal to include Jira Issue/Epic/Initiative nodes |
| `tests/test_collaboration_config.py` | Add tests for new layers |

### New collaboration layers

```python
# In config.py — add to LAYER_CONFIGS list:

CollaborationLayerConfig(
    key="jira_issue_comment_engagement",
    label="Comment Engagement (Jira Issue)",
    weight=3.0,
    description="Person A commented on a Jira Issue that Person B reported",
    category="shared_artifact",  # uses log dampening
),
CollaborationLayerConfig(
    key="jira_issue_co_commenters",
    label="Co-commenters (Jira Issue)",
    weight=2.0,
    description="Both people commented on the same Jira Issue",
    category="shared_artifact",
),
CollaborationLayerConfig(
    key="jira_epic_initiative_comment_engagement",
    label="Comment Engagement (Jira Epic/Initiative)",
    weight=2.0,
    description="Person A commented on a Jira Epic/Initiative that Person B reported",
    category="shared_artifact",
),
CollaborationLayerConfig(
    key="jira_epic_initiative_co_commenters",
    label="Co-commenters (Jira Epic/Initiative)",
    weight=1.0,
    description="Both people commented on the same Jira Epic or Initiative",
    category="shared_artifact",
),
CollaborationLayerConfig(
    key="jira_mentions",
    label="Mentions (Jira)",
    weight=2.0,
    description="Person A @mentioned Person B in a Jira Issue, Epic, or Initiative",
    category="shared_artifact",
),
```

### New Cypher sub-queries (in `collaboration_score.cypher`)

```cypher
-- jira_issue_comment_engagement
MATCH (commenter:Person)-[:COMMENTED_ON]->(issue:Issue)<-[:REPORTED_BY]-(author:Person)
WHERE issue.id STARTS WITH 'jira::Issue::'
  AND commenter.id <> author.id
WITH commenter, author, count(issue) AS cnt
RETURN commenter.id AS p1_id, author.id AS p2_id,
       log(cnt + 1) * {weight_jira_issue_comment_engagement} AS sub_score

-- jira_issue_co_commenters
MATCH (p1:Person)-[:COMMENTED_ON]->(issue:Issue)<-[:COMMENTED_ON]-(p2:Person)
WHERE issue.id STARTS WITH 'jira::Issue::'
  AND p1.id < p2.id
WITH p1, p2, count(issue) AS cnt
RETURN p1.id AS p1_id, p2.id AS p2_id,
       log(cnt + 1) * {weight_jira_issue_co_commenters} AS sub_score

-- jira_epic_initiative_comment_engagement
MATCH (commenter:Person)-[:COMMENTED_ON]->(entity)<-[:REPORTED_BY]-(author:Person)
WHERE (entity:Epic OR entity:Initiative)
  AND entity.id STARTS WITH 'jira::'
  AND commenter.id <> author.id
WITH commenter, author, count(entity) AS cnt
RETURN commenter.id AS p1_id, author.id AS p2_id,
       log(cnt + 1) * {weight_jira_epic_initiative_comment_engagement} AS sub_score

-- jira_epic_initiative_co_commenters
MATCH (p1:Person)-[:COMMENTED_ON]->(entity)<-[:COMMENTED_ON]-(p2:Person)
WHERE (entity:Epic OR entity:Initiative)
  AND entity.id STARTS WITH 'jira::'
  AND p1.id < p2.id
WITH p1, p2, count(entity) AS cnt
RETURN p1.id AS p1_id, p2.id AS p2_id,
       log(cnt + 1) * {weight_jira_epic_initiative_co_commenters} AS sub_score

-- jira_mentions
MATCH (author:Person)-[:REPORTED_BY|ASSIGNED_TO]-(entity)-[:MENTIONS]->(mentioned:Person)
WHERE (entity:Issue OR entity:Epic OR entity:Initiative)
  AND entity.id STARTS WITH 'jira::'
  AND author.id <> mentioned.id
WITH author, mentioned, count(entity) AS cnt
RETURN author.id AS p1_id, mentioned.id AS p2_id,
       log(cnt + 1) * {weight_jira_mentions} AS sub_score
```

### Phase 4 gate

```bash
pytest -m unit tests/test_collaboration_config.py -v -k "jira_comment or jira_mention"
```

**Test coverage:**
- `test_jira_issue_comment_engagement_layer_registered` — layer exists in config
- `test_jira_issue_co_commenters_layer_registered`
- `test_jira_epic_initiative_comment_engagement_layer_registered`
- `test_jira_epic_initiative_co_commenters_layer_registered`
- `test_jira_mentions_layer_registered`
- `test_all_comment_layers_have_correct_weights` — cross-check weights match plan
- `test_existing_layers_unchanged` — no regressions in existing layer count/weights

---

## Phase 5: Documentation + AI prompt

**Goal**: Update `neo4j_prompt.md` so the AI agent knows about these relationships on Jira entities.

### Files to modify

| File | Changes |
|---|---|
| `src/app/ai_agent/neo4j_prompt.md` | Add `COMMENTED_ON` and `MENTIONS` to Work Items relationship list; add note about aggregated properties |

### Detailed changes

In the **Relationships** section, update the Work Items line:

```markdown
# Before:
**Work Hierarchy**: PART_OF, ASSIGNED_TO, REPORTED_BY, TEAM, IN_SPRINT, BLOCKS, DEPENDS_ON, RELATES_TO

# After:
**Work Hierarchy**: PART_OF, ASSIGNED_TO, REPORTED_BY, TEAM, IN_SPRINT, BLOCKS, DEPENDS_ON, RELATES_TO, COMMENTED_ON (has `count`, `first_interaction_at`, `last_interaction_at`), MENTIONS
```

Also add a note in the **Key Constraints** section:
```markdown
- COMMENTED_ON on Issues/Epics/Initiatives uses snapshot semantics: edges are
  replaced on each sync with aggregated count and timestamp properties.
```

### Phase 5 gate

Manual review: read `neo4j_prompt.md` and verify the relationships are documented correctly.

---

## Phase 6: Integration validation

**Goal**: End-to-end validation with a real Jira instance.

### Manual validation steps

1. **Run the Jira producer with comments enabled:**
   ```bash
   docker compose run --rm jira-producer
   ```

2. **Verify Neo4j state:**
   ```cypher
   // Check COMMENTED_ON edges exist on Jira Issues
   MATCH (p:Person)-[c:COMMENTED_ON]->(i:Issue)
   WHERE i.id STARTS WITH 'jira::Issue::'
   RETURN p._display_name, i.key, c.count, c.first_interaction_at, c.last_interaction_at
   LIMIT 10

   // Check COMMENTED_ON edges exist on Jira Epics
   MATCH (p:Person)-[c:COMMENTED_ON]->(e:Epic)
   WHERE e.id STARTS WITH 'jira::Epic::'
   RETURN p._display_name, e.key, c.count
   LIMIT 10

   // Check MENTIONS edges exist
   MATCH (entity)-[:MENTIONS]->(p:Person)
   WHERE entity:Issue OR entity:Epic OR entity:Initiative
   RETURN entity.key, labels(entity), p._display_name
   LIMIT 10
   ```

3. **Run incremental sync and verify idempotency:**
   ```bash
   docker compose run --rm jira-producer  # second run
   ```
   Verify comment counts haven't doubled.

4. **Verify collaboration scores include new layers:**
   Run the collaboration score query and check that Jira comment-based scores appear.

5. **Verify catalog queries work:**
   Run each new catalog query from the Query Catalog UI.

---

## Files summary

### Created (9 files)

| File | Phase |
|---|---|
| `tests/producers/jira/__init__.py` | 1 |
| `tests/producers/jira/test_fetch_jira_comments.py` | 1 |
| `tests/producers/jira/test_map_jira_mentions.py` | 1 |
| `tests/producers/jira/test_build_signals_with_comments.py` | 2 |
| `tests/test_consumer_jira_comments.py` | 3 |
| `queries_catalog/jira/issue_comment_participants.yaml` | 4 |
| `queries_catalog/jira/epic_initiative_comment_engagement.yaml` | 4 |
| `queries_catalog/cross_domain/cross_platform_comment_activity.yaml` | 4 |
| `queries_catalog/jira/mentioned_people_jira.yaml` | 4 |

### Modified (8 files)

| File | Phase |
|---|---|
| `src/connectors/producers/jira/fetch_jira.py` | 1 |
| `src/connectors/producers/jira/map_jira.py` | 1 |
| `src/connectors/producers/jira/main.py` | 2 |
| `src/connectors/neo4j_db/models.py` | 3 |
| `src/app/analytics/collaboration/config.py` | 4 |
| `src/app/analytics/collaboration/queries/collaboration_score.cypher` | 4 |
| `queries_catalog/cross_domain/team_knowledge_surface_area.yaml` | 4 |
| `src/app/ai_agent/neo4j_prompt.md` | 5 |

---

## Risk mitigation

| Risk | Mitigation |
|---|---|
| JQL `updated >=` returns too many results on first incremental run | The `last_synced_at` cursor is set AFTER a successful full run, so the first incremental run only catches changes since the last full run |
| ADF parsing misses some mention formats | Verbose DEBUG logging dumps extracted mentions; manual validation catches gaps |
| Comment API rate limiting on large Jira instances | `JIRA_FETCH_COMMENTS=false` env var allows disabling; per-entity fetch naturally spaces out calls |
| Snapshot pattern deletes all COMMENTED_ON edges on each sync | This is by design — the signal carries the authoritative full set. The GitHub producer works the same way |