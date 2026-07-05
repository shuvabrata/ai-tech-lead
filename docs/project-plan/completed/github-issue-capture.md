# Plan: GitHub Issue Capture for ActivitySignal Pipeline

**Status:** Phases 1–6 complete — all done
**Created:** 2026-07-04
**Phases:** 6
**Tracking:** Use the checkboxes below to track progress during implementation.

---

## TL;DR

Extend the existing GitHub producer (`src/connectors/producers/github/`) to fetch GitHub issues and emit `ActivitySignal` events reusing the existing `Issue` entity type / `IssueAttributes` model / `Issue` Neo4j label (distinguished by `source='github'` and WBA key prefix `github::Issue::`). Capture the full human-interaction surface: assignees, reporter, comments, @mentions, cross-references to Jira/GitHub issues, and repo linkage. Fix a latent `i.source='jira'` hardcode bug in `merge_issue` and add snapshot-interaction aggregation for `COMMENTED_ON` edges. Add 2 new collaboration-network layers (issue comment engagement + co-commenters) and 6 new query-catalog queries. 6 phases, each with a unit-test gate.

---

## Decisions (resolved during interview)

| # | Decision | Choice |
|---|---|---|
| 1 | Entity type reuse | Reuse `Issue` / `IssueAttributes` / `:Issue` label; distinguish by `source='github'` |
| 2 | Issue `id` / `key` format | `id` = `"<repo_full_name>#<number>"` (e.g. `myorg/my-repo#42`); WBA key = `github::Issue::myorg/my-repo#42`; `key` attribute = same as `id` |
| 3 | Attribute mapping | Reuse `IssueAttributes` as-is. `type="Issue"`, `priority="None"`, `story_points=None`. `assignee` = primary assignee login, `reporter` = author login. `labels` = list of label names. `custom=None`. |
| 4 | Relationships | Full set: `ASSIGNED_TO` (per assignee), `REPORTED_BY`, `PART_OF`→Repository, `MENTIONS`, `REFERENCES`, `RELATES_TO`, `COMMENTED_ON` (per comment, direction="IN", timestamp property) |
| 5 | Comment handling | Single Issue signal with ALL relationships (including COMMENTED_ON), mirroring `build_pull_request_signal.py` exactly. No separate comments pass. |
| 6 | Fetch strategy | Search API (`is:issue updated:>=`) for incremental + `repo.get_issues(state="all")` fallback for first sync. Terminal-state handling via `updated:>=` filter (closed issues with no changes have stale `updated_at`). |
| 7 | Mentions/references parsing | Regex on issue body + comment bodies. Reuse `extract_issue_keys()` for Jira keys. New `extract_github_issue_refs()` for `#42` / `org/repo#99`. New `extract_mentions()` for `@login`. Strip code blocks first. Dedup across body+comments. |
| 8 | `RELATES_TO` vs `REFERENCES` | GitHub issue → GitHub issue = `RELATES_TO`; GitHub issue → Jira issue = `REFERENCES`. Derived from text refs (no timeline API). |
| 9 | Self-reference handling | Skip self-refs (author mentioning themselves → skip MENTIONS; issue referencing itself → skip RELATES_TO). Keep ASSIGNED_TO for self-assignment. |
| 10 | Mentioned non-collaborators | Emit MENTIONS edges to all mentioned logins; consumer auto-creates stub Person nodes (existing behavior). |
| 11 | `COMMENTED_ON` direction | `direction="IN"` (mirrors PR producer). Stored edge: `(Person)-[:COMMENTED_ON]->(Issue)`. |
| 12 | Other relationship directions | `MENTIONS`, `REFERENCES`, `RELATES_TO`, `ASSIGNED_TO`, `REPORTED_BY`, `PART_OF` all `direction=None` (undirected, project default per `RELATIONSHIPS_DESIGN.md`). |
| 13 | Dedup scope | Dedup MENTIONS/REFERENCES/RELATES_TO across body+comments per target id. COMMENTED_ON: one edge per comment (with timestamp) — consumer aggregates via `replace_snapshot_interaction_relationships`. |
| 14 | `custom` dict | `custom=None`. Comment count lives on the aggregated COMMENTED_ON edge (`r.count`). `reactions_total` omitted (REACTED_TO deferred). |
| 15 | Consumer changes | **Required.** (a) Add `source: str = 'jira'` field to `Issue` dataclass; populate from `signal.source` in `_handle_issue`. (b) Replace hardcoded `i.source = 'jira'` with `i.source = $source` (always overwrite — preserves stub enrichment). (c) Use `replace_snapshot_interaction_relationships` for COMMENTED_ON in `merge_issue` (mirrors `merge_pull_request`). |
| 16 | RabbitMQ routing | No new queue. GitHub issue signals publish to existing `github_queue` (only 3 queues exist: `github_queue`, `jira_queue`, `confluence_queue`). Consumer dispatches via existing `_HANDLERS["Issue"]`. |
| 17 | Sync cursor | Reuse existing per-repo cursor (`get_sync_cursor('github', full_name)`). Cursor advances only after all entity types succeed. |
| 18 | GitHub Projects | Skip. Link to Repository only via `PART_OF`. GitHub Projects V2 requires GraphQL (deferred). |
| 19 | Collaboration network | Add Layer 13 (GitHub Issue Comment Engagement, weight 3) + Layer 14 (GitHub Issue Co-commenters, weight 2), filtered to `issue.id STARTS WITH 'github::Issue::'`. Existing Layer 1 (reporter-assignee) picks up GitHub issues automatically. Defer MENTIONS/REFERENCES/RELATES_TO/co-assignee layers. |
| 20 | Collab network config | 2 new flags: `include_github_issue_comment_engagement` (default True), `include_github_issue_co_commenters` (default True). Plus weight params (3 and 2). |
| 21 | Query catalog | 6 new queries in `queries_catalog/github/`: open_issues_by_repository, issues_by_label, issue_age_by_repository, issue_to_code_linkage, issue_comment_participants, cross_referenced_issues. |
| 22 | Testing | Unit tests mirroring `test_github_producer_phase4.py`. All marked `@pytest.mark.unit`. Integration tests deferred to Phase 6. |
| 23 | Phasing | 6 phases (Fetch, Map, Builder, Orchestrator+Consumer, Collab Network, Queries+E2E+Docs). |
| 24 | Logging | Verbose `INFO` and `DEBUG` logs throughout all new/modified code, using the existing `from common.logger import logger`. Follow the PR producer's logging patterns. |

---

## Steps (6 phases)

### Phase 1 — Fetch layer
*Parallel with Phase 2*

- [x] 1.1 Add `fetch_issues(github_obj, repo_full_name, since_date)` to `src/connectors/producers/github/fetch_github.py` — Search API (`is:issue updated:>=` filter) with pagination via `retry_with_backoff`. Filter out PRs (`issue.pull_request` truthy).
- [x] 1.2 Add `fetch_issues_direct(repo_obj)` to `fetch_github.py` — `repo.get_issues(state="all", sort="updated", direction="desc")` fallback for first sync / Search API failure.
- [x] 1.3 Add `fetch_issue_comments(issue)` to `fetch_github.py` — `list(issue.get_comments())` via `retry_with_backoff`.
- [x] 1.4 Add `resolve_issues_since_date(last_synced_at)` helper (mirrors `resolve_prs_since_date`). Log the resolved cutoff date at INFO level.
- [x] 1.5 Add verbose `INFO`/`DEBUG` logging to all fetch functions: `logger.info("Fetching issues for '%s' since %s ...", repo_full_name, since_date)` at start; `logger.info("  Fetched %d issues (total: %d)", len(batch), len(all_issues))` per page; `logger.debug("Issue #%d: pull_request=%s", issue.number, bool(issue.pull_request))` per issue during PR filtering; `logger.info("Found %d total issues", len(all_issues))` at end. Use `from common.logger import logger` — never `print()`.
- [x] 1.6 **Tests:** `tests/test_github_issue_fetch.py` — mock PyGithub, assert `is:issue` filter, `updated:>=` filter, pagination, PR exclusion, fallback path. Mark `@pytest.mark.unit`.
- [x] 1.7 **Gate:** `pytest -m unit tests/test_github_issue_fetch.py -q` passes.

### Phase 2 — Map layer + parsing helpers
*Parallel with Phase 1*

- [x] 2.1 Add `map_issue(issue, repo_full_name)` to `src/connectors/producers/github/map_github.py` — raw PyGithub issue → normalized dict (`key`, `summary`, `priority="None"`, `status`, `type="Issue"`, `created_at`, `updated_at`, `assignee`, `reporter`, `labels`, `url`).
- [x] 2.2 Add `extract_github_issue_refs(text, repo_full_name)` to `map_github.py` — parse `#42` (resolve to `<repo>#42`) and `org/repo#99` from text. Strip fenced code blocks first. Return deduplicated list.
- [x] 2.3 Add `extract_mentions(text)` to `map_github.py` — parse `@login` (GitHub login regex). Strip code blocks first. Return deduplicated list.
- [x] 2.4 Reuse existing `extract_issue_keys(text)` for Jira keys (already in `map_github.py`).
- [x] 2.5 Add `_strip_code_blocks(text)` helper used by both `extract_github_issue_refs` and `extract_mentions`. Log at DEBUG level the number of code blocks stripped and the text length before/after stripping.
- [x] 2.6 Add verbose `DEBUG` logging to parsing helpers: `logger.debug("Extracted %d mentions from text (len=%d)", len(mentions), len(text))`, `logger.debug("Extracted %d GitHub issue refs: %s", len(refs), refs)`, `logger.debug("Extracted %d Jira issue keys: %s", len(keys), keys)`. Use `from common.logger import logger`.
- [x] 2.7 **Tests:** `tests/test_github_issue_map.py` — mapping, mention extraction (with/without code blocks), reference extraction (same-repo `#42` → `<repo>#42`, cross-repo `org/repo#99`), Jira key extraction reuse, dedup. Mark `@pytest.mark.unit`.
- [x] 2.8 **Gate:** `pytest -m unit tests/test_github_issue_map.py -q` passes.

### Phase 3 — Signal builder
*Depends on Phase 1 + Phase 2*

- [x] 3.1 Create `src/connectors/producers/github/build_issue_signal.py` with `build_issue_signal(issue_data, repo_data, assignee_logins, mention_logins, referenced_jira_keys, referenced_github_issue_ids, relates_to_ids, comments_data) -> Optional[ActivitySignal]`.
- [x] 3.2 Build `IssueAttributes` with: `key=f"{repo_full_name}#{number}"`, `summary=_truncate(title)`, `priority="None"`, `status` (open/closed), `type="Issue"`, `created_at`, `updated_at`, `story_points=None`, `assignee` (primary, first assignee), `reporter` (author login), `labels`, `url`, `custom=None`.
- [x] 3.3 Emit relationships:
  - `ASSIGNED_TO` (`direction=None`) — one per assignee login.
  - `REPORTED_BY` (`direction=None`) — author login.
  - `PART_OF` (`direction=None`) — target `Repository` with `id=<repo_full_name>`.
  - `MENTIONS` (`direction=None`) — one per unique mentioned login (skip self-refs where mention == author).
  - `REFERENCES` (`direction=None`) — one per unique Jira key (target `jira::Issue::<key>`).
  - `RELATES_TO` (`direction=None`) — one per unique GitHub issue ref (target `github::Issue::<repo>#<number>`, skip self-refs).
  - `COMMENTED_ON` (`direction="IN"`, `properties={"timestamp": comment.created_at}`) — one per comment.
- [x] 3.4 `id=f"{repo_full_name}#{number}"`. `event_time` from `updated_at` (fallback `created_at`).
- [x] 3.5 Wrap in `try/except` with `logger.warning` and `return None` on failure (per producer-development-guide Phase 5).
- [x] 3.6 Add verbose `INFO`/`DEBUG` logging to the builder: `logger.info("Building Issue signal for '%s#%d' (state=%s, assignees=%d, comments=%d)", repo_full_name, number, state, len(assignee_logins), len(comments_data))` at entry; `logger.debug("Emitting %d ASSIGNED_TO, %d MENTIONS, %d REFERENCES, %d RELATES_TO, %d COMMENTED_ON relationships", ...)` before returning the signal; `logger.debug("Issue signal built: id=%s, event_time=%s", signal.id, signal.event_time)` on success. Use `from common.logger import logger`.
- [x] 3.7 **Tests:** `tests/test_github_issue_producer.py` — happy path (assert `id`, `entity_type="Issue"`, `source="github"`, relationship count/types), invalid data (returns None), multi-assignee (one ASSIGNED_TO per assignee), mention parsing (body+comments, dedup, self-ref skip), reference parsing (Jira + GitHub, dedup, self-ref skip), COMMENTED_ON emission (direction="IN", timestamp property), `custom=None`, `type="Issue"`, `priority="None"`, `story_points=None`. Mark `@pytest.mark.unit`.
- [x] 3.8 **Gate:** `pytest -m unit tests/test_github_issue_producer.py -q` passes.

### Phase 4 — Orchestrator + wiring + consumer changes
*Depends on Phase 3*

- [x] 4.1 Create `src/connectors/producers/github/process_issues.py` with `process_issues(repo, repo_data, repo_owner, full_name, last_synced_at, published, seen_persons, pub_callback)`:
  - Resolve `since_date` via `resolve_issues_since_date(last_synced_at)`.
  - Fetch via `fetch_issues` (Search API); fallback to `fetch_issues_direct` on failure.
  - For each issue: fetch comments via `fetch_issue_comments`, parse mentions/refs from body+comments, build signal, publish.
  - Emit Person signals for commenters/assignees/mentioned users not in `seen_persons` (dedup).
  - Add verbose `INFO`/`DEBUG` logging: `logger.info("Fetching issues for '%s'...", full_name)` at start; `logger.info("Fetched %d issues for '%s'", len(issues), full_name)` after fetch; `logger.debug("Processing issue '%s#%d' (%s) [%d/%d]", full_name, issue.number, issue.state, idx, total)` per issue; `logger.info("Issues done (%d) for '%s'", published.get("Issue", 0), full_name)` at end. Log Person dedup decisions at DEBUG: `logger.debug("Person '%s' already seen, skipping Person signal", login)`. Use `from common.logger import logger`.
- [x] 4.2 Wire `process_issues()` into `process_repo_signals.py` (after `process_prs`). Add `logger.info("Processing issues for '%s'...", full_name)` before the call and `logger.info("Issues processing complete for '%s'", full_name)` after.
- [x] 4.3 **Consumer changes** (critical):
  - Add `source: str = 'jira'` field to `Issue` dataclass in `src/connectors/neo4j_db/models.py`.
  - Update `_handle_issue` in `src/connectors/consumers/sinks/neo4j_sink.py` to populate `source=signal.source` on the Issue dataclass. Add `logger.debug("Handling Issue signal: id=%s, source=%s, entity_type=%s", wba_node_id(signal), signal.source, signal.entity_type)` at entry.
  - Update `merge_issue` in `src/connectors/neo4j_db/models.py`:
    - Replace `set_clauses.append("i.source = 'jira'")` with `set_clauses.append("i.source = $source")` and include `source` in `props`.
    - Replace the per-relationship `merge_relationship` loop with the snapshot pattern (mirroring `merge_pull_request`):
      ```python
      if relationships:
          interaction_rels = [r for r in relationships if r.type in ("COMMENTED_ON", "REACTED_TO")]
          other_rels = [r for r in relationships if r.type not in ("COMMENTED_ON", "REACTED_TO")]
          replace_snapshot_interaction_relationships(session, issue.id, "Issue", interaction_rels)
          for rel in other_rels:
              merge_relationship(session, rel)
      ```
    - Add `logger.debug("Merging Issue node: id=%s, source=%s, key=%s, status=%s, %d interaction_rels, %d other_rels", issue.id, issue.source, issue.key, issue.status, len(interaction_rels), len(other_rels))` before the MERGE. Use `from common.logger import logger` (or the existing `logging.getLogger(__name__)` if that's the convention in `models.py`).
- [x] 4.4 **Tests:**
  - `tests/test_github_issue_orchestrator.py` — `process_issues` with mocked fetch/build/publish, assert correct call sequence, Person dedup. Mark `@pytest.mark.unit`.
  - Extend consumer tests (`tests/test_consumer_phase5.py` or new `tests/test_consumer_github_issue.py`) — `_handle_issue` with GitHub-source Issue signal: assert node `id == "github::Issue::<repo>#<number>"`, `source == "github"`, COMMENTED_ON edges aggregated with count/first/last timestamps. Mark `@pytest.mark.unit`.
  - Verify Jira issue tests still pass (source defaults to 'jira', no regression).
- [x] 4.5 **Gate:** `pytest -m unit tests -q` passes (all existing + new tests).

### Phase 5 — Collaboration network
*Depends on Phase 4 (parallel with Phase 6)*

- [x] 5.1 Add Layer 13 (GitHub Issue Comment Engagement) to `src/app/analytics/collaboration/queries/collaboration_score.cypher`
  (added after layer 12 in the existing cypher file)
- [x] 5.2 Add Layer 14 (GitHub Issue Co-commenters)
  (added after layer 13 in the existing cypher file)
- [x] 5.3 Add config flags to `src/app/analytics/collaboration/config.py`
- [x] 5.4 Add verbose `INFO` logging to `get_collaboration_network` in `src/app/api/graph/v1/service.py`
- [x] 5.5 **Tests:** added 6 tests to `test_collaboration_config.py` (layer order, default weights, enabled by default, cypher params, selective disable)
- [x] 5.6 **Gate:** `pytest -m unit tests/ -q` = 671 passed (all existing + new)

### Phase 6 — Query catalog + end-to-end + documentation
*Depends on Phase 4 (parallel with Phase 5)*

- [x] 6.1 Add 6 queries to `queries_catalog/github/`:
  - `open_issues_by_repository.yaml` — count of open issues per repo.
  - `issues_by_label.yaml` — issues grouped by label.
  - `issue_age_by_repository.yaml` — age of open issues per repo.
  - `issue_to_code_linkage.yaml` — GitHub issues that reference commits/PRs in the same repo.
  - `issue_comment_participants.yaml` — people who commented on issues per repo.
  - `cross_referenced_issues.yaml` — GitHub issues that reference Jira issues (via REFERENCES edge).
- [x] 6.2 End-to-end verification:
  - `docker compose run --rm github-producer` against a real repo. Verify the log output shows verbose INFO/DEBUG messages for issue fetching, mapping, signal building, and publishing.
  - Verify in Neo4j Browser: `MATCH (i:Issue) WHERE i.id STARTS WITH 'github::Issue::' RETURN i.id, i.key, i.source LIMIT 20` — canonical IDs, `source='github'`.
  - Verify relationships: `MATCH (i:Issue {id: 'github::Issue::<repo>#<n>'})-[r]-(n) RETURN type(r), n.id` — ASSIGNED_TO, REPORTED_BY, PART_OF, MENTIONS, REFERENCES, RELATES_TO, COMMENTED_ON.
  - Verify no old-format IDs: `MATCH (n) WHERE n.id STARTS WITH 'identity_github_' RETURN count(n)` → 0.
  - Verify collaboration network picks up GitHub issue interactions. Check logs for Layer 13/14 pair counts.
  - Verify new query catalog queries return results.
- [x] 6.3 Documentation:
  - Regenerated `docs/design/spec-activity-signal.md` via `PYTHONPATH=src python scripts/generate_signal_activity_spec.py` (includes Issue with GitHub source).
  - Updated `docs/design/rabbitmq-design.md` — added `github.Issue` routing key example and note that no new queue is needed (wildcard `github.#` covers it).
  - Updated `docs/design/github-api-optimization.md` — added section 8 on GitHub issue incremental sync (Search API `updated:>=` filter, terminal-state handling).
- [x] 6.4 **Gate:** `pytest -m unit tests/ -q` = 671 passed (all existing + new). Query catalog loads correctly: 96 total queries, 31 GitHub queries (25 existing + 6 new issue queries).

---

## Logging Requirements

All new and modified code MUST include verbose `INFO` and `DEBUG` logs using the existing logger:

```python
from common.logger import logger
```

**Never use `print()`** — always use `logger.info()` or `logger.debug()`.

### Logging patterns to follow (mirroring the PR producer)

| Layer | Level | When | Example |
|---|---|---|---|
| Fetch | INFO | Start of fetch | `logger.info("Fetching issues for '%s' since %s ...", full_name, since_date)` |
| Fetch | INFO | Per page | `logger.info("  Fetched %d issues (total: %d)", len(batch), len(all_issues))` |
| Fetch | DEBUG | Per item | `logger.debug("Issue #%d: pull_request=%s, state=%s", number, bool(pr), state)` |
| Fetch | INFO | End of fetch | `logger.info("Found %d total issues", len(all_issues))` |
| Map | DEBUG | After parsing | `logger.debug("Extracted %d mentions, %d GitHub refs, %d Jira keys", len(m), len(g), len(j))` |
| Builder | INFO | Entry | `logger.info("Building Issue signal for '%s#%d' (state=%s, assignees=%d, comments=%d)", repo, num, state, len(a), len(c))` |
| Builder | DEBUG | Before return | `logger.debug("Issue signal built: id=%s, %d relationships", signal.id, len(signal.relationships))` |
| Builder | WARNING | On failure | `logger.warning("Skipping Issue signal for '%s#%d' (validation error): %s", repo, num, exc)` |
| Orchestrator | INFO | Start | `logger.info("Fetching issues for '%s'...", full_name)` |
| Orchestrator | DEBUG | Per issue | `logger.debug("Processing issue '%s#%d' (%s) [%d/%d]", full_name, num, state, idx, total)` |
| Orchestrator | INFO | End | `logger.info("Issues done (%d) for '%s'", published.get("Issue", 0), full_name)` |
| Consumer | DEBUG | Handler entry | `logger.debug("Handling Issue signal: id=%s, source=%s", wba_node_id(signal), signal.source)` |
| Consumer | DEBUG | Merge | `logger.debug("Merging Issue: id=%s, source=%s, %d interaction_rels, %d other_rels", ...)` |
| Collab | INFO | Startup | `logger.info("Collaboration network: GitHub issue layers %s", "enabled" if flag else "disabled")` |
| Collab | DEBUG | After layer | `logger.debug("Layer 13: %d pairs scored", pair_count)` |

### Log context

Use `LogContext` for request-scoped correlation (already used in `main.py`):

```python
from common.logger import LogContext

with LogContext(request_id=repo.full_name):
    await process_issues(...)
```

This ensures all logs within the issue processing block carry the repo full name as correlation ID, matching the existing producer pattern.

---

## Relevant files

### Producer (new files)
- `src/connectors/producers/github/build_issue_signal.py` — **new** — signal builder (Phase 3). Reference: `build_pull_request_signal.py`.
- `src/connectors/producers/github/process_issues.py` — **new** — orchestrator (Phase 4). Reference: `process_prs.py`.

### Producer (modified)
- `src/connectors/producers/github/fetch_github.py` — **modify** — add `fetch_issues`, `fetch_issues_direct`, `fetch_issue_comments`, `resolve_issues_since_date` (Phase 1). Reference: `fetch_pull_requests_search`, `fetch_pull_requests_direct`.
- `src/connectors/producers/github/map_github.py` — **modify** — add `map_issue`, `extract_github_issue_refs`, `extract_mentions`, `_strip_code_blocks` (Phase 2). Reference: `map_repo`, `extract_issue_keys`.
- `src/connectors/producers/github/process_repo_signals.py` — **modify** — wire `process_issues()` (Phase 4).

### Consumer (modified — critical)
- `src/connectors/neo4j_db/models.py` — **modify** — add `source` field to `Issue` dataclass; fix `merge_issue` (replace hardcoded `i.source = 'jira'` with `i.source = $source`; add `replace_snapshot_interaction_relationships` for COMMENTED_ON) (Phase 4). Reference: `merge_pull_request` (lines ~1580-1600), `replace_snapshot_interaction_relationships` (lines ~1661-1760).
- `src/connectors/consumers/sinks/neo4j_sink.py` — **modify** — update `_handle_issue` to populate `source=signal.source` on Issue dataclass (Phase 4). Reference: `_handle_pull_request` (line ~384).

### Collaboration network (modified)
- `src/app/analytics/collaboration/queries/collaboration_score.cypher` — **modify** — add Layer 13 + Layer 14 (Phase 5). Reference: existing Layer 11 (PR comment engagement) + Layer 12 (PR co-commenters).
- `src/app/analytics/collaboration/config.py` — **modify** — add 2 new flags + 2 weight params (Phase 5).

### Query catalog (new files)
- `queries_catalog/github/open_issues_by_repository.yaml` — **new** (Phase 6).
- `queries_catalog/github/issues_by_label.yaml` — **new** (Phase 6).
- `queries_catalog/github/issue_age_by_repository.yaml` — **new** (Phase 6).
- `queries_catalog/github/issue_to_code_linkage.yaml` — **new** (Phase 6).
- `queries_catalog/github/issue_comment_participants.yaml` — **new** (Phase 6).
- `queries_catalog/github/cross_referenced_issues.yaml` — **new** (Phase 6).

### Tests (new files)
- `tests/test_github_issue_fetch.py` — **new** (Phase 1).
- `tests/test_github_issue_map.py` — **new** (Phase 2).
- `tests/test_github_issue_producer.py` — **new** (Phase 3).
- `tests/test_github_issue_orchestrator.py` — **new** (Phase 4).
- `tests/test_consumer_github_issue.py` — **new** (Phase 4).

### Documentation (modified)
- `docs/design/spec-activity-signal.md` — **regenerate** (Phase 6).
- `docs/design/rabbitmq-design.md` — **modify** (Phase 6, if needed).
- `docs/design/github-api-optimization.md` — **modify** (Phase 6).

---

## Verification

1. **Phase 1:** `pytest -m unit tests/test_github_issue_fetch.py -q` passes.
2. **Phase 2:** `pytest -m unit tests/test_github_issue_map.py -q` passes.
3. **Phase 3:** `pytest -m unit tests/test_github_issue_producer.py -q` passes.
4. **Phase 4:** `pytest -m unit tests -q` passes (all existing + new). Verify Jira issue tests still pass (no regression from `source` field change).
5. **Phase 5:** Collaboration network runs without error; new layers 13-14 contribute scores; config flags toggle them.
6. **Phase 6:** `docker compose run --rm github-producer` exits 0. Log output shows verbose INFO/DEBUG messages for issue fetching, mapping, signal building, and publishing (verify in `logs/github-producer/`). Neo4j Browser verifies:
   - `MATCH (i:Issue) WHERE i.id STARTS WITH 'github::Issue::' RETURN i.id, i.key, i.source LIMIT 20` — canonical IDs, `source='github'`.
   - `MATCH (i:Issue {id: 'github::Issue::<repo>#<n>'})-[r]-(n) RETURN type(r), n.id` — all 7 relationship types present.
   - `MATCH (n) WHERE n.id STARTS WITH 'identity_github_' RETURN count(n)` → 0.
   - Collaboration network query returns GitHub-issue-derived scores.
   - All 6 new query catalog queries return results.

---

## Decisions (assumptions and scope)

**Included:**
- GitHub issue capture (producer + consumer fix + collab network + queries + tests + docs).
- Reuse of `Issue` entity type, `IssueAttributes`, `:Issue` label, `_handle_issue` sink.
- Full interaction surface: assignees, reporter, comments, mentions, references, relates_to, repo linkage.
- Snapshot interaction aggregation for COMMENTED_ON (mirrors PR/Confluence pattern).
- Fix for latent `i.source='jira'` hardcode bug in `merge_issue`.
- 2 new collaboration network layers (comment engagement + co-commenters).
- 6 new query catalog queries.
- Incremental sync via Search API `updated:>=` filter.

**Excluded (deferred):**
- GitHub Projects V2 linkage (requires GraphQL).
- REACTED_TO relationships (reactions).
- MENTIONS / REFERENCES / RELATES_TO / co-assignee collaboration network layers.
- New `Comment` entity type (comment content not captured as nodes; only COMMENTED_ON edges).
- Timeline events API for cross-references (regex parsing used instead).
- `story_points` / `priority` / `type` derivation from labels (always defaults).
- `comments_count` / `reactions_total` in `custom` dict (count lives on aggregated edge).

---

## Further Considerations

1. **Terminal-state optimization without Neo4j access:** The producer can't query Neo4j to pre-filter closed issues (producers never read Neo4j). The `updated:>=` Search API filter effectively handles this (closed issues with no changes have stale `updated_at` and aren't returned). If finer-grained optimization is needed later, a consumer-side hint mechanism could be added. **Recommendation:** rely on `updated:>=` filter for now.

2. **MENTIONS collaboration layer (future Layer 15):** If GitHub issue mentions prove valuable for collaboration scoring, add `(author:Person)-[:REPORTED_BY]-(issue:Issue)-[:MENTIONS]->(mentioned:Person) WHERE issue.id STARTS WITH 'github::Issue::'` as Layer 15 with weight 1. **Recommendation:** defer until comment-based layers (13-14) prove useful.

3. **Jira issue comments:** The snapshot interaction pattern added to `merge_issue` in Phase 4 enables future Jira issue comment capture (the Jira producer would emit COMMENTED_ON edges and `merge_issue` would aggregate them). **Recommendation:** note this as a future enhancement, not part of this plan.
