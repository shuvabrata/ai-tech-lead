# Query Management System - Implementation Plan

**Status**: Planning Phase  
**Created**: March 2, 2026  
**Last Updated**: March 2, 2026  
**Related**: Graph Visualization (Phase 5.2, 5.3), Future AI Query Generation

## Overview

A comprehensive query management system to store, organize, and serve Cypher queries for the Neo4j graph visualization feature. The system supports multiple query types (examples, history, favorites) with full CRUD capabilities, enabling both out-of-the-box examples and user personalization.

### Key Features
- **Example Queries**: Curated, pre-configured queries shipped with the application
- **Query History**: Automatic tracking of executed queries (Phase 5.3)
- **Favorite Queries**: User-saved queries for quick access (Phase 5.3)
- **Full CRUD API**: Create, read, update, delete operations
- **Categorization**: Tags, categories, and metadata for organization
- **Frontend Integration**: Accordion UI, history dropdown, favorites list

### Design Principles
- **Database-First**: PostgreSQL as single source of truth
- **Extensible Schema**: Support multiple query types with single table
- **REST API**: Following existing three-layer pattern (router → service → query)
- **Secure**: User-scoped data, validation, read-only query enforcement
- **Migration-Ready**: Alembic migrations for schema changes

---

## Architecture

### Database Schema

**Table**: `saved_queries`

```sql
CREATE TABLE saved_queries (
    id SERIAL PRIMARY KEY,
    query_type VARCHAR(20) NOT NULL,  -- 'example', 'history', 'favorite'
    title VARCHAR(200),                -- NULL for history entries
    description TEXT,                   -- NULL for history entries
    cypher_query TEXT NOT NULL,
    category VARCHAR(50),               -- e.g., 'relationships', 'analytics', 'admin'
    tags VARCHAR(100)[],                -- Array of tags for filtering
    metadata JSONB,                     -- Flexible storage for additional data
    is_active BOOLEAN DEFAULT TRUE,     -- Soft delete flag
    display_order INTEGER,              -- For sorting examples
    execution_count INTEGER DEFAULT 0,  -- Track popularity
    last_executed_at TIMESTAMP,         -- For history sorting
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_saved_queries_type ON saved_queries(query_type);
CREATE INDEX idx_saved_queries_category ON saved_queries(category);
CREATE INDEX idx_saved_queries_active ON saved_queries(is_active);
CREATE INDEX idx_saved_queries_last_executed ON saved_queries(last_executed_at DESC);
```

### Query Types

1. **Example Queries** (`query_type='example'`)
   - Pre-configured by developers
   - Shipped with application (seeded via migration)
   - Title, description, category required
   - `is_active=True` for visible examples
   - Sorted by `display_order`

2. **Query History** (`query_type='history'`)
   - Auto-saved on execution
   - No title/description (uses query text)
   - Limited to last 50 entries (cleanup job)
   - Sorted by `last_executed_at DESC`

3. **Favorite Queries** (`query_type='favorite'`)
   - User-created bookmarks (Phase 5.3+)
   - User provides title/description
   - Can be created from history or examples
   - Future: Add `user_id` column for multi-user support

### API Endpoints

**Base Path**: `/api/v1/queries`

| Method | Endpoint | Description | Use Case |
|--------|----------|-------------|----------|
| GET | `/examples` | List all active example queries | Phase 5.2 - Populate accordion |
| GET | `/examples/{id}` | Get specific example | View details |
| POST | `/examples` | Create new example | Admin: Add new example |
| PATCH | `/examples/{id}` | Update example | Admin: Modify existing |
| DELETE | `/examples/{id}` | Soft delete example | Admin: Hide broken query |
| GET | `/history` | List recent query history | Phase 5.3 - History dropdown |
| POST | `/history` | Save executed query to history | Auto-save on execution |
| DELETE | `/history/{id}` | Remove history entry | User cleanup |
| GET | `/favorites` | List favorite queries | Phase 5.3 - Favorites list |
| POST | `/favorites` | Create favorite | User saves query |
| PATCH | `/favorites/{id}` | Update favorite | Edit title/description |
| DELETE | `/favorites/{id}` | Remove favorite | Delete bookmark |
| POST | `/{id}/execute` | Execute saved query | One-click execution |

---

## Phase 1: Database Schema & Example Queries API

### Objectives
- Create database table for saved queries
- Implement CRUD API for example queries
- Seed initial example queries
- Test with frontend integration (Phase 5.2)

### Tasks

- [ ] **1.1 Create Database Model**
  - File: `app/db/models/saved_query.py`
  - Create SQLAlchemy model matching schema above
  - Add `QueryType` enum: `EXAMPLE`, `HISTORY`, `FAVORITE`
  - Add validation: required fields, query length limits
  - Import in `app/db/models/__init__.py`

- [ ] **1.2 Create Migration**
  - Command: `alembic revision --autogenerate -m "create saved_queries table"`
  - Review generated migration
  - Add indexes manually if not auto-detected
  - Test: `alembic upgrade head`

- [ ] **1.3 Define Pydantic Models**
  - File: `app/api/queries/v1/model.py`
  - Models:
    - `SavedQueryBase`: Common fields (title, description, cypher_query, etc.)
    - `SavedQueryCreate`: For POST requests
    - `SavedQueryUpdate`: For PATCH requests (all optional)
    - `SavedQueryResponse`: For GET responses (includes id, timestamps)
    - `ExampleQueryListResponse`: Paginated list wrapper
  - Validation: Non-empty query, max lengths, valid query_type

- [ ] **1.4 Implement Query Layer**
  - File: `app/api/queries/v1/query.py`
  - Functions:
    - `get_examples(skip: int, limit: int)` - List active examples
    - `get_example_by_id(id: int)` - Get single example
    - `create_example(data: SavedQueryCreate)` - Insert new
    - `update_example(id: int, data: SavedQueryUpdate)` - Update existing
    - `soft_delete_example(id: int)` - Set is_active=False
    - `get_examples_by_category(category: str)` - Filter by category
  - All use async SQLAlchemy sessions
  - Return ORM models

- [ ] **1.5 Implement Service Layer**
  - File: `app/api/queries/v1/service.py`
  - Functions:
    - `list_examples()` - Business logic for listing (sorting, filtering)
    - `get_example_details(id)` - Validate existence
    - `create_example_query(data)` - Validate Cypher query is read-only
    - `update_example_query(id, data)` - Validate and update
    - `delete_example_query(id)` - Soft delete with validation
  - Integrate with existing graph API query validation
  - Transform ORM models to Pydantic responses

- [ ] **1.6 Implement Router**
  - File: `app/api/queries/v1/router.py`
  - Endpoints:
    - `GET /api/v1/queries/examples` - List all examples
    - `GET /api/v1/queries/examples/{id}` - Get example
    - `POST /api/v1/queries/examples` - Create example
    - `PATCH /api/v1/queries/examples/{id}` - Update example
    - `DELETE /api/v1/queries/examples/{id}` - Delete example
  - Error handling: 404 (not found), 400 (validation), 500 (database)
  - Include router in `app/main.py`

- [ ] **1.7 Seed Example Queries**
  - File: `alembic/versions/YYYY_MM_DD_HHMM_seed_example_queries.py` (data migration)
  - Seed 6-8 useful example queries:
    1. **Show All People** (category: basic)
       - Query: `MATCH (p:Person) RETURN p LIMIT 10`
       - Description: "Display all people in the graph"
    2. **People and Projects** (category: relationships)
       - Query: `MATCH (p:Person)-[r:WORKS_ON]->(proj:Project) RETURN p, r, proj LIMIT 15`
       - Description: "Show relationships between people and their projects"
    3. **Project Dependencies** (category: relationships)
       - Query: `MATCH (p1:Project)-[r:DEPENDS_ON]->(p2:Project) RETURN p1, r, p2 LIMIT 20`
       - Description: "Visualize project dependency chains"
    4. **Recent Issues** (category: analytics)
       - Query: `MATCH (i:Issue) WHERE i.created_at > datetime() - duration('P7D') RETURN i LIMIT 25`
       - Description: "Find issues created in the last 7 days"
    5. **Active Branches** (category: code)
       - Query: `MATCH (b:Branch)-[:BELONGS_TO]->(r:Repository) WHERE b.status = 'active' RETURN b, r LIMIT 20`
       - Description: "Show active code branches and their repositories"
    6. **Node Type Summary** (category: analytics)
       - Query: `MATCH (n) RETURN labels(n) AS NodeType, count(n) AS Count ORDER BY Count DESC`
       - Description: "Count nodes by type (tabular view)"
  - Set appropriate `display_order`, `category`, `tags`

- [ ] **1.8 Create Tests**
  - File: `tests/test_queries_api.py`
  - Test coverage:
    - CRUD operations (create, read, update, delete)
    - Validation (empty query, write operations)
    - Filtering (by category, active status)
    - Error handling (not found, invalid data)
    - Seed data verification
  - Target: 25+ tests

### Verification
```bash
# List all example queries
curl http://localhost:8000/api/v1/queries/examples

# Get specific example
curl http://localhost:8000/api/v1/queries/examples/1

# Create new example (admin)
curl -X POST http://localhost:8000/api/v1/queries/examples \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Query",
    "description": "Sample description",
    "cypher_query": "MATCH (n) RETURN n LIMIT 5",
    "category": "basic",
    "query_type": "example"
  }'

# Update example
curl -X PATCH http://localhost:8000/api/v1/queries/examples/1 \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description"}'

# Delete example
curl -X DELETE http://localhost:8000/api/v1/queries/examples/1
```

---

## Phase 2: Frontend Integration (Example Queries)

### Objectives
- Display example queries in Graph page
- Click-to-populate functionality
- Track example usage

### Tasks

- [ ] **2.1 Add Accordion Component**
  - File: `app/dash_app/pages/graph.py`
  - Add `dbc.Accordion` with id `example-queries-accordion`
  - Position: Below query validation message, above Execute button
  - Accordion items created dynamically from API data
  - Each item shows: title, description, category badge, query preview
  - Collapsed by default

- [ ] **2.2 Fetch Examples from API**
  - File: `app/dash_app/pages/graph.py`
  - Add callback on page load to fetch examples
  - Endpoint: `GET /api/v1/queries/examples`
  - Store in `dcc.Store` with id `examples-data-store`
  - Handle API errors gracefully

- [ ] **2.3 Populate Accordion**
  - File: `app/dash_app/pages/graph.py`
  - Callback: `populate_examples_accordion()`
  - Input: `examples-data-store` data
  - Output: `example-queries-accordion` children
  - Group by category if needed
  - Add "Use This Query" button for each example

- [ ] **2.4 Click-to-Populate Callback**
  - File: `app/dash_app/pages/graph.py`
  - Callback: `load_example_query()`
  - Input: Button clicks from accordion items (pattern-matching callback)
  - Output: `graph-query-input` value
  - Populate textarea with selected example query
  - Optional: Close accordion after selection

- [ ] **2.5 Track Usage**
  - File: `app/dash_app/pages/graph.py`
  - When example is used, increment `execution_count`
  - Call backend API: `POST /api/v1/queries/examples/{id}/track`
  - Update `last_executed_at` timestamp
  - Use for analytics (most popular examples)

### Verification
- Open Graph page, verify accordion appears
- Click "Use This Query" button
- Verify query populates textarea
- Execute query and verify it works
- Check database: `execution_count` incremented

---

## Phase 3: Query History (Auto-Save)

### Objectives
- Auto-save executed queries
- Display recent history
- Load from history

### Tasks

- [ ] **3.1 Extend API for History**
  - File: `app/api/queries/v1/router.py`
  - Add endpoints:
    - `GET /api/v1/queries/history?limit=50`
    - `POST /api/v1/queries/history` (auto-save)
    - `DELETE /api/v1/queries/history/{id}`
  - Service layer handles history-specific logic:
    - Limit to last 50 entries
    - Auto-cleanup old entries
    - No title/description required

- [ ] **3.2 Auto-Save on Execution**
  - File: `app/dash_app/pages/graph.py`
  - Update `execute_query()` callback
  - After successful execution, save to history:
    - POST to `/api/v1/queries/history`
    - Include query text and execution timestamp
    - Silent failure (don't block on errors)

- [ ] **3.3 History Dropdown**
  - File: `app/dash_app/pages/graph.py`
  - Add `dbc.Select` with id `query-history-select`
  - Position: Above query textarea
  - Options: Last 20 queries from history API
  - Format: Truncated query text (first 50 chars)

- [ ] **3.4 Load from History**
  - File: `app/dash_app/pages/graph.py`
  - Callback: `load_history_query()`
  - Input: `query-history-select` value
  - Output: `graph-query-input` value
  - Fetch full query from history store
  - Update `last_executed_at` timestamp

- [ ] **3.5 History Cleanup**
  - File: `app/api/queries/v1/service.py`
  - Function: `cleanup_old_history(max_entries=50)`
  - Delete oldest entries beyond limit
  - Run on each history save (or background job)

### Verification
- Execute multiple queries
- Verify they appear in history dropdown
- Select from history, verify query loads
- Execute 60 queries, verify only last 50 kept

---

## Phase 4: Favorite Queries

### Objectives
- Save queries as favorites
- Organize favorites with titles/descriptions
- Quick access to favorites

### Tasks

- [ ] **4.1 Extend API for Favorites**
  - File: `app/api/queries/v1/router.py`
  - Add endpoints:
    - `GET /api/v1/queries/favorites`
    - `POST /api/v1/queries/favorites` (user creates)
    - `PATCH /api/v1/queries/favorites/{id}` (edit)
    - `DELETE /api/v1/queries/favorites/{id}` (remove)

- [ ] **4.2 Add to Favorites Button**
  - File: `app/dash_app/pages/graph.py`
  - Add "⭐ Save as Favorite" button
  - Position: Next to Execute button
  - Opens modal for title/description input

- [ ] **4.3 Favorites Modal**
  - File: `app/dash_app/pages/graph.py`
  - `dbc.Modal` with form:
    - Title input (required)
    - Description textarea (optional)
    - Category select (dropdown)
    - Tags input (optional)
  - Submit button saves to favorites API

- [ ] **4.4 Favorites List**
  - File: `app/dash_app/pages/graph.py`
  - Add `dbc.ListGroup` with id `favorites-list`
  - Position: Sidebar or separate tab
  - Each item shows: title, description, category
  - Actions: Load, Edit, Delete

- [ ] **4.5 Load from Favorites**
  - File: `app/dash_app/pages/graph.py`
  - Click favorite item loads query
  - Same as example/history functionality

### Verification
- Execute query, save as favorite
- Verify appears in favorites list
- Edit favorite (change title)
- Delete favorite
- Load favorite query

---

## Phase 5: Advanced Features (Future)

### Optional Enhancements

- [ ] **5.1 Query Templates with Parameters**
  - Support placeholders: `MATCH (p:Person {name: $name}) RETURN p`
  - UI inputs for parameter values
  - Backend parameter substitution

- [ ] **5.2 Shared Queries**
  - Export query as shareable link
  - Import from JSON/YAML
  - Team query library

- [ ] **5.3 Query Analytics**
  - Most popular examples
  - Most frequently executed queries
  - Average execution time tracking

- [ ] **5.4 Advanced Search**
  - Full-text search across queries
  - Filter by tags, category, date
  - Fuzzy matching

- [ ] **5.5 Query Versioning**
  - Track query modifications
  - Version history per favorite
  - Rollback to previous versions

---

## Data Migration Strategy

### Initial Seed (Phase 1)
```python
# alembic/versions/YYYY_MM_DD_HHMM_seed_example_queries.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.execute("""
        INSERT INTO saved_queries (
            query_type, title, description, cypher_query, 
            category, display_order, is_active
        ) VALUES
        ('example', 'Show All People', 
         'Display all people in the graph',
         'MATCH (p:Person) RETURN p LIMIT 10',
         'basic', 1, TRUE),
        -- ... more examples
    """)

def downgrade():
    op.execute("DELETE FROM saved_queries WHERE query_type = 'example'")
```

### Future Updates
- Add new examples via data migrations
- Deprecate old queries with `is_active=FALSE`
- Update categories/tags as needed

---

## Security Considerations

- **Query Validation**: All saved queries validated as read-only before storage
- **Injection Prevention**: Parameterized queries, no string interpolation
- **Soft Deletes**: Never hard-delete user data (use `is_active` flag)
- **Future User Scoping**: Add `user_id` column when multi-user support added
- **Rate Limiting**: Prevent abuse of history/favorites creation
- **Input Sanitization**: Validate title/description fields (no XSS)

---

## Testing Strategy

### Unit Tests
- Query validation (read-only enforcement)
- Model validation (Pydantic)
- Service layer logic (sorting, filtering)

### Integration Tests
- CRUD operations end-to-end
- API endpoints with real database
- Seed data verification
- History cleanup logic

### Manual Testing
- Frontend UI interactions
- Example query execution
- History auto-save
- Favorites management

---

## Success Metrics

- **Phase 1**: 6+ example queries seeded, CRUD API working
- **Phase 2**: Example queries visible in UI, click-to-populate functional
- **Phase 3**: Query history auto-saves, last 50 accessible
- **Phase 4**: Users can save/manage favorites
- **Overall**: Reduced time to execute common queries (target: <5 seconds from load to execution)

---

## Dependencies

### New
- None (uses existing PostgreSQL, SQLAlchemy, FastAPI)

### Existing
- `sqlalchemy` (async ORM)
- `alembic` (migrations)
- `fastapi` (REST API)
- `pydantic` (validation)
- `dash` (frontend)

---

## References

- Graph Visualization Implementation: `graph-visualization-implementation.md`
- Existing API patterns: `app/api/projects/v1/`, `app/api/chats/v1/`
- Database models: `app/db/models/project.py`

---

## Changelog

- **2026-03-02**: Initial planning document created
- **2026-03-02**: Defined 4-phase implementation approach
- **2026-03-02**: Designed database schema with multi-type support
- **2026-03-02**: Specified 6 initial example queries for seeding
