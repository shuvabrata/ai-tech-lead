# Plan 005: Fix Cypher Injection in Graph Expansion Endpoint
  
> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat c832d0c..HEAD -- src/app/api/graph/v1/model.py src/app/api/graph/v1/query.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `c832d0c`, 2026-06-23
- **Issue**: https://github.com/shuvabrata/work-behavior-analytics-ai/issues/167

## Why this matters

The `/api/v1/graph/expand` endpoint takes a list of `relationship_types` and interpolates them directly into a Cypher query string (e.g. `MATCH (m)-[r:{relationship_filter}]->(n)`). Because these strings are not validated, an attacker can pass arbitrary Cypher strings (like `["KNOWS]-(x) DETACH DELETE x //"]`) to execute malicious write or drop commands, bypassing the read-only checks used elsewhere. Validating these fields to only contain safe alphanumeric characters eliminates the injection vector.

## Current state

- `src/app/api/graph/v1/model.py` — Contains `NodeExpansionRequest` which currently has no regex validation on `relationship_types`.
  ```python
  # file:src/app/api/graph/v1/model.py:44
      relationship_types: Optional[List[str]] = Field(
          default=None,
          description="Filter by specific relationship types. If None, all types are included."
      )
  ```
- `src/app/api/graph/v1/query.py` — Interpolates the relationship types directly without sanitization.
  ```python
  # file:src/app/api/graph/v1/query.py:284
      if relationship_types:
          type_list = "|".join(relationship_types)
          relationship_filter = f":{type_list}"
  ```

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Install   | `poetry install` (or `pip install -r requirements_dev.txt`) | exit 0              |
| Lint      | `ruff check src/`        | exit 0              |

## Scope

**In scope**:
- `src/app/api/graph/v1/model.py`

**Out of scope**:
- Any changes to `query.py`. Fixing this at the Pydantic model validation layer is sufficient and cleaner.

## Git workflow

- Branch: `advisor/005-fix-cypher-injection`
- Commit message style: `fix: add regex validation to relationship_types to prevent Cypher injection`

## Steps

### Step 1: Add validation to NodeExpansionRequest

In `src/app/api/graph/v1/model.py`, import `re` and `field_validator` from Pydantic (if not already imported), and add a validation method to `NodeExpansionRequest` to ensure all strings in `relationship_types` contain only alphanumeric characters and underscores.

Modify `NodeExpansionRequest`:
```python
import re
from pydantic import BaseModel, Field, field_validator

class NodeExpansionRequest(BaseModel):
    # ... existing fields ...
    relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by specific relationship types. If None, all types are included."
    )
    
    @field_validator("relationship_types")
    @classmethod
    def validate_relationship_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            for rel_type in v:
                if not re.match(r"^[A-Za-z0-9_]+$", rel_type):
                    raise ValueError(f"Invalid relationship type: {rel_type}. Must be alphanumeric.")
        return v
```

**Verify**: `python -c "from app.api.graph.v1.model import NodeExpansionRequest; NodeExpansionRequest(node_id='1', direction='both', relationship_types=['VALID_TYPE'])"` → should not raise an error.
**Verify**: `python -c "from app.api.graph.v1.model import NodeExpansionRequest; NodeExpansionRequest(node_id='1', direction='both', relationship_types=['INVALID]-(x)'])"` → should raise `ValidationError`.

## Done criteria

- [ ] `relationship_types` strictly validates against `^[A-Za-z0-9_]+$`
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- The Pydantic version doesn't support `@field_validator` (e.g. it's Pydantic v1 using `@validator`). (If so, use `@validator`).
