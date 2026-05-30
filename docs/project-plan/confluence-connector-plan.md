# Confluence Connector Integration Plan

**Status**: In Progress
**Goal**: Integrate Confluence into the event-driven architecture to capture knowledge management collaboration signals and map them to the Neo4j graph. The scope of this plan includes:
1. Identifying relevant Confluence concepts.
2. Defining the Activity Signal payload structure.
3. Defining Node and relationship properties for the Neo4j graph.
4. Identifying suitable Python programming libraries.
5. Defining the necessary backend and frontend changes.
6. Defining a comprehensive test strategy.

## Background
This project plan builds upon the existing architecture defined in several core design documents:
- **[Graph DB High-Level Design](../../docs/design/graph-db-high-level-design.md)**: Identifies Confluence integration as Phase 5, initially targeting `Space` and `Page` nodes to track knowledge management insights.
- **Activity Signal Specification**: Defines the standardized event payload that the new Confluence producer must emit.
- **Relationships Design**: Guides our data modeling decisions, emphasizing direct relationships to maintain graph query performance.

## 1. Decisions Log

### Decision 1: Scope of Collaboration Signals (Agreed)
We will capture the following human-to-human and human-to-artifact signals:
1. **Co-authorship / Edits**: Capturing who creates and modifies pages.
2. **Page Comments**: Capturing who is discussing the content.
3. **Explicit Mentions**: Capturing when a person pulls another person into a document (@mentions).
4. **Likes / Reactions**: Capturing interest, alignment, and passive knowledge consumption.
5. **Cross-Artifact Linking**: Capturing explicit links from Confluence Pages to Jira Issues or GitHub Repositories.

### Decision 1.5: Core Confluence Concepts & Hierarchy (Agreed)
We will model `Space`, `Page`, and `Blogpost`, capturing the page tree hierarchy. 
* **Space**: The root container.
* **Page**: The document.
* **Blogpost**: Included because reactions (comments, likes) to broadcast communications provide valuable alignment signals.

### Decision 2: Graph Data Modeling (Agreed)
We will use direct relationships for interactions to maintain a simple and performant graph, avoiding standalone nodes for comments and reactions. We will not capture comment text, but we will track the status of comments to measure ambiguity resolution.
* `(Person)-[:CREATED]->(Page)`
* `(Person)-[:MODIFIED]->(Page)`
* `(Person)-[:COMMENTED_ON {timestamp, status}]->(Page)` (status: open, resolved, closed)
* `(Person)-[:REACTED_TO {type: "like", timestamp}]->(Page)`
* `(Page)-[:MENTIONS]->(Person)`
* `(Page)-[:REFERENCES]->(Issue)`
* `(Page)-[:IN_SPACE]->(Space)`
* `(Page)-[:CHILD_OF]->(Page)`
* `(Blogpost)` nodes will share the same interaction relationships as `(Page)` (CREATED, MODIFIED, COMMENTED_ON, REACTED_TO, MENTIONS, REFERENCES) and will link to the Space via `(Blogpost)-[:IN_SPACE]->(Space)`.

### Decision 3: Activity Signal Payload Structure (Agreed)
We will use **Delta / Interaction Signals** to prevent payload bloat over RabbitMQ.
* The Confluence Producer will track a `last_synced_at` timestamp.
* It will only fetch and emit new interactions (comments, likes, edits) that occurred since the last sync.
* Base entities (`Page`, `Space`, `Blogpost`) will be emitted when their core metadata changes.
* The Neo4j consumer will merge these incoming delta relationships onto the existing nodes.

### Decision 4: Node Properties (Agreed)
We will store essential metadata and URLs, but **strictly exclude** the actual body content (HTML/Storage format) from the Neo4j graph for this MVP.
* **Space**: `id` (canonical WBA ID), `key` (e.g., "ENG"), `name`, `type` (e.g., "global", "personal"), `url`.
* **Page / Blogpost**: `id` (canonical WBA ID), `title`, `url`, `created_at`, `last_updated_at`, `version` (integer to track edit churn frequency), and `status` (e.g., "current", "archived", "draft").

### Decision 5: Python API Library (Agreed)
We will use the `atlassian-python-api` library in the Confluence Producer to handle API communication.
* **Reason**: It provides out-of-the-box support for the Confluence REST API (handling pagination and retries natively), significantly reducing boilerplate code for the MVP.

### Decision 6: Extraction Scope & Authentication (Agreed)
Configuration will be designed for senior leaders, defaulting to full-instance discovery rather than requiring manual per-space entry.
* **Authentication**: `url` (Base URL), `email`, and `api_token` (Atlassian API token).
* **Scope**: Discover and extract all Spaces by default.
* **Filtering**: Provide `include_spaces` and `exclude_spaces` fields (lists of space keys) in the configuration to allow users to narrow the scope if needed (e.g., excluding HR or Finance spaces).
* **Backend/Frontend Impact**: Update `ConfluenceConfigItemRequest` Pydantic models and the Dash frontend form to support these specific fields.

### Decision 7: Identity Resolution (Agreed)
We will resolve identities using `email` as the primary key whenever available, falling back to the Atlassian `accountId`.
* **Primary**: `email` (takes precedence because it is the global cross-system identifier in our graph, easily matching with GitHub and Jira identities).
* **Fallback**: Atlassian `accountId` (used when email is hidden by Atlassian privacy settings).
* **Identity Mapping**: The consumer will use our existing `IdentityMapping` logic to merge these into central `Person` nodes.

### Decision 8: Testing Strategy (Agreed)
We will enforce a strict testing strategy that prioritizes local determinism over live system dependencies to prevent flaky builds in CI/CD.
* **Unit Testing the Producer (Mocked API)**: Heavily mock `atlassian-python-api` using static JSON fixtures. Assert correct translation to `ActivitySignal` payloads and proper delta sync (`last_synced_at`) logic.
* **Unit Testing the Consumer (Mocked DB)**: Mock the Neo4j `Session` to assert that correct Cypher queries are executed, correct dataclasses are built, and identity resolution fallback logic works as expected.
* **No Live E2E Tests for MVP**: Explicitly exclude live end-to-end tests against an actual Atlassian Cloud instance in the automated suite to avoid rate-limiting and mutation-based flakiness. Rely on manual E2E verification during development.

## 2. Implementation Phases (Agreed)
We will structure the implementation into five sequential phases to safely roll out the connector:
* **Phase 0: Pre-requisite - Access & Validation**
  - [x] Create API access tokens for Confluence using a test account.
  - [x] Write a sample Python program using `atlassian-python-api` to validate authentication and successful connection to the workspace.
* **Phase 1: Shared Schema & Graph Models**
  - [x] Update `src/common/activity_signal/models.py` with `Space`, `Page`, and `Blogpost` attribute payloads.
  - [x] Update `src/connectors/neo4j_db/models.py` with new dataclasses and `merge_space`, `merge_page`, `merge_blogpost` functions.
  - [x] Update `src/app/scripts/create_es_indexes.py` to add Confluence entities to `MANAGED_INDEXES` ensuring they are searchable.
* **Phase 2: Configuration API & Frontend**
  - [x] Update the `ConfluenceConfig` SQLAlchemy model in `app/db/models/connector_configs.py` to support `url`, `email`, `encrypted_api_token`, `include_spaces`, and `exclude_spaces`.
  - [x] Generate and apply an Alembic database migration.
  - [x] Update the backend connectors API and Pydantic models to support the new schema.
  - [x] Update the Dash Connectors UI form to accept the URL, email, API token, and space filters.
* **Phase 3: The Confluence Producer**
  - [ ] Build the extraction script using `atlassian-python-api`.
    - **Prep Decision**: Use `asyncio.to_thread()` to wrap synchronous API calls to maintain the async producer pipeline.
    - **Prep Decision**: Structure fetching logic into distinct functions (e.g., `fetch_spaces`, `fetch_cql_results`) in `fetch_confluence.py` mirroring the prep script.
  - [ ] Implement the delta sync logic using the `last_synced_at` cursor.
    - **Prep Decision**: Utilize Confluence Query Language (CQL) (e.g., `lastModified >= "YYYY-MM-DD"`) for efficient fetching of recently changed Pages and Blogposts.
  - [ ] Parse page bodies for inline relationships.
    - **Prep Decision**: Use `BeautifulSoup` (with `lxml`) to parse the `body.storage` format and reliably extract `@mentions` and Jira macro links.
  - [ ] Emit the bundled delta `ActivitySignal` payloads to RabbitMQ.
* **Phase 4: The Neo4j Consumer**
  - [ ] Add handlers in `src/connectors/consumers/sinks/neo4j_sink.py` to parse incoming Confluence signals and call the new merge functions.

## 3. Technology & Packages
* **Producer API Client**: `atlassian-python-api`
* **Message Broker**: RabbitMQ (existing infrastructure)