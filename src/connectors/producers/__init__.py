"""GitHub and Jira producers for the ActivitySignal event-driven ingestion pipeline.

Phase 3: Contains decoupled fetch_* and map_* utilities extracted from the legacy
connector handlers. Phase 4 will add producer entrypoints that use these utilities
to publish ActivitySignal payloads to RabbitMQ.
"""
