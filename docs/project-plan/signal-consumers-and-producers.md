# Implementation Plan: ActivitySignal Event-Driven Ingestion

## Vision
Transition the current monolithic data ingestion architecture (fetch & write) into an event-driven, decoupled system. This will be achieved by introducing RabbitMQ as a message broker, building generic producers for GitHub and Jira that emit standardized `ActivitySignal` JSON payloads, and building a universal Neo4j consumer that reads these signals and upserts them into the graph database. 

Legacy modules will remain intact and functional during this transition to ensure stability. Over time, the legacy direct-to-DB modules will be deprecated.

---

## Phase 1: Infrastructure Setup (RabbitMQ)
**Goal:** Provision the message broker to handle ActivitySignal events.

- [ ] **Docker Compose Update:** Add a `rabbitmq` service to `docker-compose.yml` using the `rabbitmq:3.13-management` image. Expose port `15672` for the Management UI and add health checks. Add dependency in the `app` container.
- [ ] **Environment Configuration:** Add RabbitMQ connection variables to `.env.example` and expose the RabbitMQ URL to FastAPI settings via `src/app/settings.py`.
- [ ] **Queue/Exchange Initialization (App Container):**
  - Create an initialization script (`src/app/scripts/init_rabbitmq.py`) that runs during the `app` container startup sequence.
  - **Exchange Definition:** Create a `topic` exchange named `activity_signals`.
  - **Routing Strategy:** Standardize routing keys as `<source>.<entity_type>` (e.g., `github.PullRequest`, `jira.Issue`).
  - **Queue Definition:** Declare a durable queue `neo4j_ingestion_queue`.
  - **Binding:** Bind `neo4j_ingestion_queue` to the `activity_signals` exchange using the routing key `#` (wildcard for all sources and entities) so the Neo4j consumer receives all graph data.

---

## Phase 2: ActivitySignal Core Library
**Goal:** Establish the strict schema and utilities required by the `spec-activity-signal.md` document.

- [ ] **Pydantic Schema Definition:** Create `src/common/activity_signal/models.py`.
  - Define the base `ActivitySignal` Pydantic model with strict validation for `signal_id`, `source`, `entity_type`, `external_id`, `attributes`, and `relationships`.
  - Enforce the mandatory attributes for each `entity_type` (e.g., Issue, Commit, Person) as defined in Section 4 of the spec.
  - Enforce relationship types (`BELONGS_TO`, `ASSIGNED_TO`, etc.) as defined in Section 5.
- [ ] **RabbitMQ Utility Module:** Create `src/common/messaging/rabbitmq.py`.
  - Implement an asynchronous publisher (`RabbitMQPublisher`) to batch and send Pydantic models as JSON to the exchange.
  - Implement an asynchronous consumer (`RabbitMQConsumer`) to listen to the queue and yield valid Pydantic models.

---

## Phase 3: Decoupling Existing Modules (Refactoring for Reuse)
**Goal:** Separate API fetching logic from DB writing logic in the existing `src/connectors/modules/` without breaking their legacy functionality.

- [ ] **GitHub Module Refactoring:**
  - Extract the raw data fetching logic (GitHub API pagination, rate-limiting, etc.) into reusable `fetch_*` service functions or clients.
  - Ensure the legacy entrypoint continues to call these `fetch_*` functions and passes the results to the old Neo4j writing functions.
- [ ] **Jira Module Refactoring:**
  - Extract the Jira REST/GraphQL fetching logic into reusable `fetch_*` service functions.
  - Keep the legacy Jira entrypoint intact, relying on the newly decoupled fetch functions.

---

## Phase 4: Building the Producers
**Goal:** Create the new event-driven entrypoints that utilize the decoupled fetchers to generate `ActivitySignal` payloads.

*Location: `src/connectors/producers/`*

- [ ] **GitHub Producer (`github_producer.py`):**
  - Import the decoupled GitHub fetchers.
  - For each entity (Repository, Branch, Commit, PullRequest, Person), map the raw API JSON to the `ActivitySignal` Pydantic model.
  - Map GitHub relations to the allowed relationship types (e.g., PR -> `AUTHORED_BY` -> Person, Commit -> `PART_OF` -> Branch).
  - Generate UUIDs for `signal_id` and attach standard metadata (`source_config`, `version`, timestamps).
  - Publish signals to RabbitMQ.
- [ ] **Jira Producer (`jira_producer.py`):**
  - Import the decoupled Jira fetchers.
  - Map Jira entities (Project, Initiative, Epic, Issue, Sprint, Person) to the `ActivitySignal` model.
  - Map Jira relations (e.g., Issue -> `BELONGS_TO` -> Epic, Issue -> `ASSIGNED_TO` -> Person).
  - Publish signals to RabbitMQ.

---

## Phase 5: Building the Neo4j Consumer
**Goal:** Build a robust, generic consumer that pulls `ActivitySignals` and populates the graph database idempotently.

*Location: `src/consumers/neo4j_consumer.py`*

- [ ] **Event Loop & Ingestion:**
  - Connect to the `neo4j_ingestion_queue` using the `RabbitMQConsumer` utility.
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