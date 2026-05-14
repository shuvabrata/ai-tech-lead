# Implementation Plan: ActivitySignal Event-Driven Ingestion

## Vision
Transition the current monolithic data ingestion architecture (fetch & write) into an event-driven, decoupled system. This will be achieved by introducing RabbitMQ as a message broker, building generic producers for GitHub and Jira that emit standardized `ActivitySignal` JSON payloads, and building specific Neo4j consumers for each entity type that read these signals and upsert them into the graph database. 

Legacy modules will remain intact and functional during this transition to ensure stability. Over time, the legacy direct-to-DB modules will be deprecated.

---

## Phase 1: Infrastructure Setup (RabbitMQ)
**Goal:** Provision the message broker to handle ActivitySignal events.

- [x] **Docker Compose Update:** Add a `rabbitmq` service to `docker-compose.yml` using the `rabbitmq:4-management` image. Expose port `15672` for the Management UI and add health checks. Add dependency in the `app` container.
- [x] **Environment Configuration:** Add RabbitMQ connection variables to `.env.example` and expose the RabbitMQ URL to FastAPI settings via `src/app/settings.py`.
- [x] **Queue/Exchange Initialization (Docker Entrypoint):**
  - Create an initialization script (`src/app/scripts/init_rabbitmq.py`).
  - Update the existing `src/app/entrypoint.sh` script to execute the initialization script (`python app/scripts/init_rabbitmq.py`) before starting the Uvicorn web server.
  - **Exchange Definition:** Create a `topic` exchange named `activity_signals`.
  - **DLQ Setup:** Create a dead-letter exchange (e.g., `activity_signals_dlx`) and a generic DLQ bound to it (e.g., `activity_signals_dlq`).
  - **Routing Strategy:** Standardize routing keys as `<source>.<entity_type>` (e.g., `github.PullRequest`, `jira.Issue`).
  - **Queue Definition (SQS-Like Behavior):** Declare classic durable queues for each entity type (e.g., `github_pullrequest_queue`, `jira_issue_queue`). *(Classic queues chosen over Quorum Queues for simplicity; single-node deployment.)*
    - Set `x-dead-letter-exchange` to `activity_signals_dlx` (DLQ routing).
    - Poison-message handling via `nack(requeue=False)` — equivalent to `x-delivery-limit` on classic queues.
    - *Note on Visibility Timeout:* Handled natively by RabbitMQ's unacknowledged state + `consumer_timeout` (default 30 mins) to requeue messages if a consumer hangs.
  - **Bindings:** Bind each specific queue to the `activity_signals` exchange using exact routing keys (e.g., bind `github_pullrequest_queue` with routing key `github.PullRequest`, `jira_issue_queue` with `jira.Issue`).
- [x] **Persistence Guarantees:**
  - **Exchanges:** Explicitly set `durable=True` when declaring `activity_signals` and `activity_signals_dlx` so they survive broker restarts.
  - **Messages:** Ensure producers set `delivery_mode=2` (Persistent) when publishing, guaranteeing messages are flushed to disk before the broker acknowledges the publisher.
- [x] **Testing & Validation (Phase 1 Infra):**
  - Write an integration test to verify RabbitMQ connectivity and successful initialization of exchanges and queues.
  - **Visibility Test:** Publish a test message, consume it without acknowledging, and verify it remains invisible to other consumers but gets requeued if the connection drops.
  - **DLQ Test:** Publish a test message, deliberately `nack(requeue=False)` it, and verify it successfully routes to the## Phase 2: ActivitySignal Core Library
**Goal:** Establish the strict schema and utilities required by the `spec-activity-signal.md` document.

- [x] **Pydantic Schema Definition:** Create `src/common/activity_signal/models.py`.
  - Complete. All entity models, discriminated unions, and relationship schemas implemented per spec.
- [x] **RabbitMQ Utility Module:** Create `src/common/messaging/rabbitmq.py`.
  - Complete. Async publisher and consumer utilities implemented and validated.

**Status:** Phase 2 is complete. All core models and messaging utilities are ready for use by producers and consumers.



**Transition note:**
Phase 3 will extract pure fetch and map logic from the legacy GitHub and Jira handlers, so that network I/O and data transformation are reusable and testable. The legacy direct-to-Neo4j code will remain for now, but will call the new `fetch_*` and `map_*` functions internally. This enables the new event-driven producers to reuse the same logic without touching the database directly.

---

---

## Phase 3: Decoupling Existing Modules (Fetch & Map Extraction)
**Goal:** Separate network I/O (fetching) and data parsing (mapping) from the database writing logic in the existing `src/connectors/modules/`. 

### Design Recommendations for Fetch/Map Extraction

**1. Grouping fetch/map utilities:**
  - Group by source (e.g., `fetch_github.py`, `map_github.py`, `fetch_jira.py`, `map_jira.py`).
  - *Rationale:* Keeps integration logic together, simplifies maintenance, and matches how APIs evolve. If a source grows large, split by entity later.

**2. Handling special entities/edge cases:**
  - Design the mapping layer to allow per-entity or per-field overrides (e.g., helper functions or a registry pattern).
  - *Rationale:* Both Jira and GitHub have custom fields and sub-resources. A flexible mapping layer supports these without cluttering main logic and is future-proof.

**3. Return type for mapping functions:**
  - Return validated `ActivitySignal` Pydantic models from mapping functions.
  - *Rationale:* Ensures schema correctness, catches errors early, and makes downstream code simpler and safer.

These recommendations ensure maintainability, extensibility, and schema safety as the ingestion pipeline evolves.

*Note on `*handler.py` files:* The existing handlers (e.g., `new_issue_handler.py`) tightly couple data parsing with Neo4j Cypher execution. The new Phase 5 Neo4j Consumers will **not** reuse these handlers, as Phase 5 relies on generic `ActivitySignal` upserts. Therefore, this phase focuses on extracting the *parsing/mapping* logic out of the handlers so the new Producers can reuse it, while leaving the DB write logic isolated as legacy code.

*Architectural Design Note (Streaming ETL):* This refactoring deliberately shifts the system toward a **Decoupled, Event-Driven Streaming ETL** pipeline:
- **Extract (`fetch_*`):** Isolates network I/O, allowing API fetching to run optimally without database bottlenecks.
- **Transform (`map_*`):** Creates pure, testable functions that convert raw JSON into standardized `ActivitySignal` dictionaries.
- **Load (Publish/Subscribe):** By decoupling the load phase (now handled downstream by Phase 5 consumers), the system gains resilience (backpressure handling), idempotency (safe replays), and extensible multi-sink capabilities (e.g., adding an Elasticsearch consumer for free).

- [x] **GitHub Module Refactoring:**
  - **Fetchers:** Extract raw data fetching logic (GitHub API pagination, GraphQL, rate-limiting) into reusable `fetch_*` service functions.
  - **Mappers:** Isolate the data transformation logic (e.g., identifying parent commits, extracting PR reviewers from raw JSON) into pure `map_*` functions that return standardized dictionaries.
  - **Legacy Wiring:** Ensure the legacy entrypoint continues to call `fetch_*` -> `map_*` -> and passes the results to the old Neo4j writing functions to maintain stability.
- [x] **Jira Module Refactoring:**
  - **Fetchers:** Extract the Jira REST API fetching and pagination logic into reusable `fetch_*` service functions.
  - **Mappers:** Extract field resolution and entity mapping out of files like `new_issue_handler.py` into pure `map_*` functions. 
    - *Crucial:* This mapping layer must resolve dynamic custom fields (like the `customfield_10020` Sprint issue documented in `TODO.md`) before returning the data dictionary.
  - **Legacy Wiring:** Keep the legacy Jira handlers intact, but strip them of parsing logic so they rely on the decoupled fetchers and mappers, acting purely as database executors.
- [x] **Testing & Validation (Phase 3):**
  - **Test Migration:** Review existing automated unit tests for legacy handlers (e.g., GitHub/Jira tests in the `tests/` directory). Extract the data transformation assertions and adapt them into new automated unit tests specifically targeting the pure `map_*` functions.
  - **Regression Testing:** Run the full existing automated test suite (using `pytest`) to guarantee that the legacy direct-to-db logic continues to function perfectly after decoupling.

---

## Phase 4: Building the Producers
**Goal:** Create the new event-driven entrypoints that utilize the decoupled fetchers and mappers to generate standardized `ActivitySignal` payloads.

**Status:** Phase 4 is complete. Producers are implemented, dockerized, validated with Phase 4 tests, and verified publishing to RabbitMQ with expected routing keys.

*Location: `src/connectors/producers/`*

- [x] **Producer State Management (The Sync Cursor):**
  - Implement a lightweight persistence mechanism (e.g., a table in the existing Postgres DB or a persistent SQLite volume) for the producers to store their `last_synced_at` timestamps per repository/project.
  - **Crucial:** The producers must *never* query Neo4j to find their sync state, maintaining strict decoupling from the consumers.
- [x] **GitHub Producer (`github_producer.py`):**
  - Import the decoupled GitHub `fetch_*` and `map_*` utilities.
  - For each entity (Repository, Branch, Commit, PullRequest, Person), convert the mapped data into the strict `ActivitySignal` Pydantic model.
  - **Validation Handling:** If a mapped entity is missing mandatory attributes (per Spec Section 4), log a warning and skip publishing to prevent poisoning the queue.
  - Map GitHub relations to the allowed relationship types (e.g., PR -> `AUTHORED_BY` -> Person, Commit -> `PART_OF` -> Branch). Generate flexible `target` lookup dicts. Direction is optional and defaults to `OUT`.
  - Generate UUIDs for `signal_id` and attach standard metadata (`source_config`, `connector_url`, `version`).
  - **Event Time Mapping:** Explicitly map the entity's source `updated_at` (or `created_at` if new) to the `event_time` to ensure correct temporal ordering downstream.
  - **Payload Truncation:** Truncate excessively large text fields (e.g., PR bodies, long commit messages) to a safe limit (e.g., 2000 chars) before adding them to `attributes`, keeping the signal lightweight.
  - Publish signals individually (no batching) to RabbitMQ using the `RabbitMQPublisher`, dynamically constructing the routing key as `<source>.<entity_type>` (e.g., `github.PullRequest`).
- [x] **Jira Producer (`jira_producer.py`):**
  - Import the decoupled Jira `fetch_*` and `map_*` utilities.
  - Convert mapped Jira entities (Project, Initiative, Epic, Issue, Sprint, Person) into the strict `ActivitySignal` Pydantic model.
  - **Validation Handling:** Drop and log entities missing mandatory attributes to enforce schema strictness.
  - Map Jira relations generating flexible `target` lookup dicts. Direction is optional and defaults to `OUT`.
  - Generate UUIDs for `signal_id` and attach standard metadata (`source_config`, `connector_url`, `version`).
  - **Event Time Mapping:** Explicitly map the Jira issue's `updated` (or `created`) field to `event_time`.
  - **Payload Truncation:** Truncate excessively large fields (e.g., Jira issue descriptions) to protect broker and database memory.
  - Publish signals individually (no batching) to RabbitMQ using the `RabbitMQPublisher`, setting the routing key as `jira.<entity_type>`.
- [x] **Runtime & Dockerization:**
  - Architect `github_producer.py` and `jira_producer.py` to be executable as standalone Python processes.
  - Create Dockerfile(s) for the producers (e.g., `Dockerfile.producer`) to package them with minimal dependencies required for fetching and publishing.
  - Update `docker-compose.yml` to include the producers as independent services (e.g., `github-producer`, `jira-producer`), passing the necessary environment variables (RabbitMQ connection, API credentials).
- [x] **Testing & Validation (Phase 4):**
  - **Unit Testing:** Review existing producer scripts/tests and add new automated unit tests. Mock the `fetch_*` utilities and verify that `map_*` outputs are correctly transformed into valid `ActivitySignal` Pydantic models. Ensure schema violations correctly log and skip without crashing the process.
  - **Routing Verification:** Mock the `RabbitMQPublisher` to assert that messages are published individually and that routing keys (e.g., `github.PullRequest`) are constructed perfectly.
  - **Container Dry-Run:** Build the producer Docker container and execute a local dry-run to ensure the standalone loop initializes, connects to the API, and prepares to publish without failing.

---

## Phase 5: Building the ActivitySignal Consumers
**Goal:** Build robust, scalable consumers that pull ActivitySignals from their respective queues and populate downstream databases idempotently. While Neo4j is the initial backend, the architecture must remain sink-agnostic to easily support future databases (e.g., Elasticsearch, InfluxDB).

*Location: `src/connectors/consumers/main.py` and `src/connectors/consumers/sinks/neo4j_sink.py`*

### Phase 5 Architecture Decisions (Confirmed)

| Decision | Resolution |
|---|---|
| **Idempotency store** | Store `_last_signal_id` and `_last_event_time` directly on Neo4j nodes. Skip property updates if incoming `event_time <= n._last_event_time`. No secondary store needed. |
| **Out-of-order update policy** | Last-write-wins on `event_time`. Older signals never overwrite newer node properties. |
| **Invalid signal handling** | DLQ-only for v1. `RabbitMQConsumer` already nacks invalid payloads to `activity_signals_dlq`. |
| **Consumer deployment shape** | One consumer process per source: `github-consumer` listens to all 6 `github_*_queue` queues; `jira-consumer` listens to all 6 `jira_*_queue` queues. Multiple container instances are supported — RabbitMQ round-robins across them. |
| **Initial queue list** | All 12 queues active from day one (producers already publish to all of them). |
| **Relationship direction** | `direction=None` → undirected edge, stored once, queried with `-[:REL]-`. `direction="OUT"` → `(node)-[:REL]->(target)`. `direction="IN"` → `(node)<-[:REL]-(target)`. **Never default `None` to `OUT`.** |
| **Node identity / MERGE key** | MERGE on `external_id` used as `id`. Legacy system is being deprecated; no backward-compat bridging needed. Neo4j constraints remain `id`-based. |
| **Relationship types to support** | Only what producers currently emit: `PART_OF`, `AUTHORED_BY`, `MERGED_INTO`, `REVIEWS`. Extend as new relationship types are added to producers. |
| **Dockerfiles** | `Dockerfile.github-consumer` and `Dockerfile.jira-consumer` (separate images per source). |

- [x] **Event Loop & Ingestion:**
  - Connect to all source-specific entity queues using the `RabbitMQConsumer` utility (one consumer process per queue, all started concurrently via `asyncio.gather`).
  - `RabbitMQConsumer` already validates incoming JSON against `ActivitySignal` and nacks failures to the DLQ — no additional validation layer needed.
  - **Metadata Injection:** The consumer injects `ingestion_time` via `signal.with_ingestion_time()` immediately after receipt.
- [x] **Neo4j Sink Implementation (`neo4j_sink.py`):**
  - **Canonical Node Upsert:** `MERGE` nodes on `{id: external_id}` (legacy `id` field). Set all `attributes` dict fields as node properties dynamically. Always set `_last_signal_id` and `_last_event_time` on every upsert.
  - **Idempotency Guard:** Before applying property updates, check `n._last_event_time`. If the incoming `event_time` is not newer, skip the SET clause (but still process relationships — they are additive).
  - **Relationship Handling:** For each `Relationship` in the signal: if `direction=None` store a single directed edge `(node)-[:REL]->(target)` by convention and query it undirected; `direction="OUT"` → `(node)-[:REL]->(target)`; `direction="IN"` → `(target)-[:REL]->(node)`. All relationship MERGEs use `MERGE` (idempotent).
  - **Stub Nodes:** Target nodes referenced in relationships that don't exist yet are created as stubs containing only `{id: external_id, source: source, _stub: true}`. The stub flag is removed when the full signal for that node arrives.
- [x] **Runtime, Dockerization & Deployment Topology:**
  - Consumer entry point (`main.py`) reads `LISTEN_QUEUES` env var (comma-separated queue names) and launches one async consumer task per queue.
  - Create `Dockerfile.github-consumer` and `Dockerfile.jira-consumer`.
  - **Deployment Strategy:** Add `github-consumer` and `jira-consumer` services to `docker-compose.yml`. Each service sets `LISTEN_QUEUES` to its 6 source-specific queues.
  - **Horizontal Scaling:** No code changes needed — RabbitMQ automatically round-robins messages across multiple container instances of the same service.
- [x] **Testing & Validation (Phase 5):**
  - **Unit Testing:** Mock the Neo4j driver and `RabbitMQConsumer`. Assert correct Cypher MERGE queries for each entity type, stub node creation, idempotency guard (older event_time → skip SET), and all three direction cases.
  - **Integration Testing:** Run a local containerized consumer, publish test signals to RabbitMQ, and verify the data accurately reflects in Neo4j.

---

## Phase 6: Testing, Rollout & Deprecation
**Goal:** Validate the new pipeline under failure conditions and plan the removal of legacy systems.

- [ ] **Error & Scale Testing:**
  - Test partial network failures, RabbitMQ restarts, and out-of-order event publishing.
  - Ensure the Consumer creates stub nodes successfully and resolves them when the actual node signal arrives.
- [x] **DLQ Remediation & Operations:**
  - Create a utility script (`src/app/scripts/redrive_dlq.py`) capable of inspecting messages in the `activity_signals_dlq` and re-publishing them to the main exchange after consumer bugs are fixed.
- [x] **End-to-End Observability:**
  - Implement structured logging in both the Producers and Consumers.
  - Ensure the `signal_id` is logged as a correlation ID at every step (fetch, publish, consume, upsert) to enable tracing of an event across the distributed system boundary.
- [x] **Automated Regression Suite Integration:**
  - Ensure all new automated tests (Phases 3, 4, and 5) are integrated into the main `pytest` test suite.
  - Run the full suite to verify a 100% pass rate across both the new event-driven system and existing features before considering the rollout complete.
- [x] **Deprecation:**
  - Update documentation to mark `src/connectors/modules/*` direct-to-db entrypoints as deprecated.
  - Schedule the removal of the old `write_to_neo4j()` legacy code once the event-driven system proves stable in production.