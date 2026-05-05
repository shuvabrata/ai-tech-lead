# Implementation Plan: ActivitySignal Event-Driven Ingestion

## Vision
Transition the current monolithic data ingestion architecture (fetch & write) into an event-driven, decoupled system. This will be achieved by introducing RabbitMQ as a message broker, building generic producers for GitHub and Jira that emit standardized `ActivitySignal` JSON payloads, and building specific Neo4j consumers for each entity type that read these signals and upsert them into the graph database. 

Legacy modules will remain intact and functional during this transition to ensure stability. Over time, the legacy direct-to-DB modules will be deprecated.

---

## Phase 1: Infrastructure Setup (RabbitMQ)
**Goal:** Provision the message broker to handle ActivitySignal events.

- [ ] **Docker Compose Update:** Add a `rabbitmq` service to `docker-compose.yml` using the `rabbitmq:3.13-management` image. Expose port `15672` for the Management UI and add health checks. Add dependency in the `app` container.
- [ ] **Environment Configuration:** Add RabbitMQ connection variables to `.env.example` and expose the RabbitMQ URL to FastAPI settings via `src/app/settings.py`.
- [ ] **Queue/Exchange Initialization (Docker Entrypoint):**
  - Create an initialization script (`src/app/scripts/init_rabbitmq.py`).
  - Update the existing `src/app/entrypoint.sh` script to execute the initialization script (`python app/scripts/init_rabbitmq.py`) before starting the Uvicorn web server.
  - **Exchange Definition:** Create a `topic` exchange named `activity_signals`.
  - **DLQ Setup:** Create a dead-letter exchange (e.g., `activity_signals_dlx`) and a generic DLQ bound to it (e.g., `activity_signals_dlq`).
  - **Routing Strategy:** Standardize routing keys as `<source>.<entity_type>` (e.g., `github.PullRequest`, `jira.Issue`).
  - **Queue Definition (SQS-Like Behavior):** Declare specific **Quorum Queues** for each entity type (e.g., `github_pullrequest_queue`, `jira_issue_queue`). 
    - Set `x-dead-letter-exchange` to `activity_signals_dlx` (DLQ routing).
    - Set `x-delivery-limit` to handle poison messages (analogous to SQS `maxReceiveCount`).
    - *Note on Visibility Timeout:* Handled natively by RabbitMQ's unacknowledged state + `consumer_timeout` (default 30 mins) to requeue messages if a consumer hangs.
  - **Bindings:** Bind each specific queue to the `activity_signals` exchange using exact routing keys (e.g., bind `github_pullrequest_queue` with routing key `github.PullRequest`, `jira_issue_queue` with `jira.Issue`).
- [ ] **Persistence Guarantees:**
  - **Exchanges:** Explicitly set `durable=True` when declaring `activity_signals` and `activity_signals_dlx` so they survive broker restarts.
  - **Messages:** Ensure producers set `delivery_mode=2` (Persistent) when publishing, guaranteeing messages are flushed to disk before the broker acknowledges the publisher.
- [ ] **Testing & Validation (Phase 1 Infra):**
  - Write an integration test to verify RabbitMQ connectivity and successful initialization of exchanges and queues.
  - **Visibility Test:** Publish a test message, consume it without acknowledging, and verify it remains invisible to other consumers but gets requeued if the connection drops.
  - **DLQ Test:** Publish a test message, deliberately `nack` (reject) it with `requeue=true` repeatedly until it hits the `x-delivery-limit`, and verify it successfully routes to the DLQ.

---

## Phase 2: ActivitySignal Core Library
**Goal:** Establish the strict schema and utilities required by the `spec-activity-signal.md` document.

- [ ] **Pydantic Schema Definition:** Create `src/common/activity_signal/models.py`.
  - Define the base `ActivitySignal` Pydantic model with strict validation for the core identifiers (`signal_id`, `source`, `entity_type`, `external_id`) AND the required metadata fields per Section 6 of the spec (`source_config`, `connector_url`, `event_time`, `version`). *Note: `ingestion_time` is excluded from the Producer model as it is set by the Consumer.*
  - Use **Pydantic Discriminated Unions** to enforce the mandatory attributes for each `entity_type` (e.g., Issue, Commit, Person) as defined in Section 4 of the spec. Create specific sub-models for attributes (e.g., `CommitAttributes`, `IssueAttributes`) configured to allow extra custom fields (`model_config = ConfigDict(extra='allow')`).
  - Enforce relationship types (`BELONGS_TO`, `ASSIGNED_TO`, etc.) as defined in Section 5.
  - **Flexible Relationship Targets:** Ensure the relationship `target` schema allows flexible lookup dictionaries (e.g., just an `email` field to identify a Person). It should NOT strictly enforce the `(source, entity_type, external_id)` tuple.
- [ ] **RabbitMQ Utility Module:** Create `src/common/messaging/rabbitmq.py`.
  - Implement an asynchronous publisher (`RabbitMQPublisher`) to send individual Pydantic models as JSON to the exchange. **Note:** Batching is intentionally NOT supported to keep payloads small and optimize RabbitMQ performance.
  - Implement an asynchronous consumer (`RabbitMQConsumer`) to listen to the queue and yield valid Pydantic models.
    - **Ingestion Time:** The Consumer is responsible for injecting the `ingestion_time` timestamp upon successfully receiving the message.
    - **Error Handling (Nack & DLQ):** If a message fails Pydantic validation, or if the consumer encounters any other failure, the utility must `nack` the message so that RabbitMQ routes it to the Dead Letter Queue (DLQ).

---

## Phase 3: Decoupling Existing Modules (Fetch & Map Extraction)
**Goal:** Separate network I/O (fetching) and data parsing (mapping) from the database writing logic in the existing `src/connectors/modules/`. 

*Note on `*handler.py` files:* The existing handlers (e.g., `new_issue_handler.py`) tightly couple data parsing with Neo4j Cypher execution. The new Phase 5 Neo4j Consumers will **not** reuse these handlers, as Phase 5 relies on generic `ActivitySignal` upserts. Therefore, this phase focuses on extracting the *parsing/mapping* logic out of the handlers so the new Producers can reuse it, while leaving the DB write logic isolated as legacy code.

*Architectural Design Note (Streaming ETL):* This refactoring deliberately shifts the system toward a **Decoupled, Event-Driven Streaming ETL** pipeline:
- **Extract (`fetch_*`):** Isolates network I/O, allowing API fetching to run optimally without database bottlenecks.
- **Transform (`map_*`):** Creates pure, testable functions that convert raw JSON into standardized `ActivitySignal` dictionaries.
- **Load (Publish/Subscribe):** By decoupling the load phase (now handled downstream by Phase 5 consumers), the system gains resilience (backpressure handling), idempotency (safe replays), and extensible multi-sink capabilities (e.g., adding an Elasticsearch consumer for free).

- [ ] **GitHub Module Refactoring:**
  - **Fetchers:** Extract raw data fetching logic (GitHub API pagination, GraphQL, rate-limiting) into reusable `fetch_*` service functions.
  - **Mappers:** Isolate the data transformation logic (e.g., identifying parent commits, extracting PR reviewers from raw JSON) into pure `map_*` functions that return standardized dictionaries.
  - **Legacy Wiring:** Ensure the legacy entrypoint continues to call `fetch_*` -> `map_*` -> and passes the results to the old Neo4j writing functions to maintain stability.
- [ ] **Jira Module Refactoring:**
  - **Fetchers:** Extract the Jira REST API fetching and pagination logic into reusable `fetch_*` service functions.
  - **Mappers:** Extract field resolution and entity mapping out of files like `new_issue_handler.py` into pure `map_*` functions. 
    - *Crucial:* This mapping layer must resolve dynamic custom fields (like the `customfield_10020` Sprint issue documented in `TODO.md`) before returning the data dictionary.
  - **Legacy Wiring:** Keep the legacy Jira handlers intact, but strip them of parsing logic so they rely on the decoupled fetchers and mappers, acting purely as database executors.

---

## Phase 4: Building the Producers
**Goal:** Create the new event-driven entrypoints that utilize the decoupled fetchers and mappers to generate standardized `ActivitySignal` payloads.

*Location: `src/connectors/producers/`*

- [ ] **GitHub Producer (`github_producer.py`):**
  - Import the decoupled GitHub `fetch_*` and `map_*` utilities.
  - For each entity (Repository, Branch, Commit, PullRequest, Person), convert the mapped data into the strict `ActivitySignal` Pydantic model.
  - **Validation Handling:** If a mapped entity is missing mandatory attributes (per Spec Section 4), log a warning and skip publishing to prevent poisoning the queue.
  - Map GitHub relations to the allowed relationship types (e.g., PR -> `AUTHORED_BY` -> Person, Commit -> `PART_OF` -> Branch). Generate flexible `target` lookup dicts. Direction is optional and defaults to `OUT`.
  - Generate UUIDs for `signal_id` and attach standard metadata (`source_config`, `connector_url`, `version`).
  - **Event Time Mapping:** Explicitly map the entity's source `updated_at` (or `created_at` if new) to the `event_time` to ensure correct temporal ordering downstream.
  - **Payload Truncation:** Truncate excessively large text fields (e.g., PR bodies, long commit messages) to a safe limit (e.g., 2000 chars) before adding them to `attributes`, keeping the signal lightweight.
  - Publish signals individually (no batching) to RabbitMQ using the `RabbitMQPublisher`, dynamically constructing the routing key as `<source>.<entity_type>` (e.g., `github.PullRequest`).
- [ ] **Jira Producer (`jira_producer.py`):**
  - Import the decoupled Jira `fetch_*` and `map_*` utilities.
  - Convert mapped Jira entities (Project, Initiative, Epic, Issue, Sprint, Person) into the strict `ActivitySignal` Pydantic model.
  - **Validation Handling:** Drop and log entities missing mandatory attributes to enforce schema strictness.
  - Map Jira relations generating flexible `target` lookup dicts. Direction is optional and defaults to `OUT`.
  - Generate UUIDs for `signal_id` and attach standard metadata (`source_config`, `connector_url`, `version`).
  - **Event Time Mapping:** Explicitly map the Jira issue's `updated` (or `created`) field to `event_time`.
  - **Payload Truncation:** Truncate excessively large fields (e.g., Jira issue descriptions) to protect broker and database memory.
  - Publish signals individually (no batching) to RabbitMQ using the `RabbitMQPublisher`, setting the routing key as `jira.<entity_type>`.
- [ ] **Runtime & Dockerization:**
  - Architect `github_producer.py` and `jira_producer.py` to be executable as standalone Python processes.
  - Create Dockerfile(s) for the producers (e.g., `Dockerfile.producer`) to package them with minimal dependencies required for fetching and publishing.
  - Update `docker-compose.yml` to include the producers as independent services (e.g., `github-producer`, `jira-producer`), passing the necessary environment variables (RabbitMQ connection, API credentials).
- [ ] **Testing & Validation (Phase 4):**
  - **Unit Testing:** Mock the `fetch_*` utilities and verify that `map_*` outputs are correctly transformed into valid `ActivitySignal` Pydantic models. Ensure schema violations correctly log and skip without crashing the process.
  - **Routing Verification:** Mock the `RabbitMQPublisher` to assert that messages are published individually and that routing keys (e.g., `github.PullRequest`) are constructed perfectly.
  - **Container Dry-Run:** Build the producer Docker container and execute a local dry-run to ensure the standalone loop initializes, connects to the API, and prepares to publish without failing.

---

## Phase 5: Building the Neo4j Consumers
**Goal:** Build robust, entity-specific consumers that pull ActivitySignals from their respective queues and populate the graph database idempotently.

*Location: `src/consumers/neo4j_consumer.py`*

- [ ] **Event Loop & Ingestion:**
  - Connect to the specific entity queues (e.g., `github_pullrequest_queue`) using the `RabbitMQConsumer` utility.
  - Validate incoming JSON against the `ActivitySignal` Pydantic model. Route invalid signals to a Dead Letter Queue (DLQ) or quarantine table.
- [ ] **Canonical Node Upsert Logic:**
  - Implement logic to `MERGE` nodes based *strictly* on the canonical identity composite key: `(source, entity_type, external_id)`.
  - Use `SET` to update properties dynamically from the `attributes` dictionary.
  - Handle deduplication (ignore messages if `signal_id` has already been processed/logged).
- [ ] **Relationship & Stub Node Handling:**
  - For each item in the `relationships` array, implement a `MERGE` for the relationship (`type`, `direction`).
  - Implement **Stub Nodes**: If a relationship references a target `(source, entity_type, external_id)` that doesn't exist yet, create it as a "stub" (a node containing *only* the canonical identity), ensuring out-of-order events do not fail the insertion.
- [ ] **Idempotency & Event Log Tracking:**
  - Log processed `signal_id`s in Neo4j or a secondary store (Redis/Postgres) to ensure strictly at-least-once or exactly-once semantics.
  - Process signals using `event_time` to prevent older signals from overwriting newer attributes.

---

## Phase 6: Testing, Rollout & Deprecation
**Goal:** Verify data parity and plan the removal of legacy systems.

- [ ] **Data Parity Testing:**
  - Run the legacy modules on a test repository/project and snapshot the Neo4j graph.
  - Clear the DB, run the new Producer -> RabbitMQ -> Consumer pipeline on the same repo/project.
  - Compare the resulting graph structures (Node counts, edge counts, properties) to ensure fidelity.
- [ ] **Error & Scale Testing:**
  - Test partial network failures, RabbitMQ restarts, and out-of-order event publishing.
  - Ensure the Consumer creates stub nodes successfully and resolves them when the actual node signal arrives.
- [ ] **Deprecation:**
  - Update documentation to mark `src/connectors/modules/*` direct-to-db entrypoints as deprecated.
  - Schedule the removal of the old `write_to_neo4j()` legacy code once the event-driven system proves stable in production.