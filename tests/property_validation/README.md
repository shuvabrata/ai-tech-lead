# Property Validation Test Suite

Comprehensive test suite that validates property population across all Neo4j nodes and relationships against the dataclass definitions in [db/models.py](../../db/models.py).

## Overview

This test suite automatically:
1. **Discovers** all entity types from `db/models.py` using Python introspection
2. **Identifies** which properties are required vs. optional (using type hints)
3. **Queries** Neo4j to count property population for each entity/relationship
4. **Categorizes** results into three buckets:
   - **FULL** (100% populated)
   - **PARTIAL** (1-99% populated)  
   - **EMPTY** (0% populated)
5. **Generates** console, JSON, and HTML reports
6. **Fails** only if required properties are 0% populated

## Key Features

✅ **Zero Configuration** - Dynamically discovers entities from code  
✅ **Self-Maintaining** - Adapts automatically as `db/models.py` evolves  
✅ **Optional Detection** - Uses `typing.Optional[T]` to identify non-required fields  
✅ **Comprehensive** - Validates both node and relationship properties  
✅ **Multi-Format Reports** - Console (colored), JSON, and HTML outputs  

## Usage

### Run the Test Suite

```bash
# Basic run
pytest tests/property_validation/test_property_validation.py -v

# With console output (recommended)
pytest tests/property_validation/test_property_validation.py -v -s

# Run specific test
pytest tests/property_validation/test_property_validation.py::test_validate_all_properties -v
```

### Environment Variables

The test requires Neo4j connection credentials:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="your_password"
```

Or use a `.env` file in the project root.

### Output Files

Reports are generated in `tests/property_validation/results/`:
- `report.json` - Machine-readable validation results
- `report.html` - Interactive HTML report with search and sorting

## Test Cases

### 1. `test_validate_all_properties`
**Purpose:** Ensure all required properties have at least some population.  
**Fails if:** Any required property is 0% populated across all nodes.  
**Example failure:**
```
❌ Person.email: REQUIRED property is empty in all 150 nodes
```

### 2. `test_generate_reports`
**Purpose:** Generate console, JSON, and HTML validation reports.  
**Verifies:** Report files are created successfully.

### 3. `test_no_entity_types_missed`
**Purpose:** Sanity check that model introspection is working.  
**Fails if:** Less than 10 entity types discovered (indicates introspection failure).

### 4. `test_partial_population_warning`
**Purpose:** Warn about required properties with incomplete population.  
**Never fails:** Only prints warnings for data quality issues.  
**Example warning:**
```
⚠️  Issue.story_points: 67.3% populated (49/150 nodes missing)
```

## Report Examples

### Console Output

```
================================================================================
PROPERTY VALIDATION REPORT
Generated: 2026-02-07 14:30:00
================================================================================

SUMMARY
  Entity Types: 13
  Relationship Types: 8
  Total Properties: 147
  ✓ Full Population (100%): 98
  ⚠ Partial Population (1-99%): 35
  ✗ Empty (0%): 14
  ✓ No failures

================================================================================
ENTITY PROPERTIES
================================================================================

Person
--------------------------------------------------------------------------------
Property                       Required   Total    Populated  Empty    %        Category
--------------------------------------------------------------------------------
id                             YES        150      150        0        100.00%  FULL
name                           YES        150      150        0        100.00%  FULL
email                          no         150      142        8        94.67%   PARTIAL
title                          YES        150      150        0        100.00%  FULL
...
```

### HTML Report Features

- **Searchable** - Filter by entity, property, or category
- **Sortable** - Click column headers to sort
- **Color-coded** - Visual distinction for FULL/PARTIAL/EMPTY
- **Summary Stats** - Dashboard view of overall health
- **Failure Badges** - Required empty properties highlighted

## Architecture

### Module Structure

```
tests/property_validation/
├── __init__.py                    # Package initialization
├── models.py                      # Data models for results
├── model_inspector.py             # Introspect db/models.py
├── relationship_inspector.py      # Discover relationships from Neo4j
├── query_generator.py             # Generate Cypher queries
├── validator.py                   # Execute validation
├── report_generator.py            # Console/JSON/HTML reports
└── README.md                      # This file
```

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Model Introspection                                          │
│    - Import db/models.py                                        │
│    - Find all @dataclass entities                               │
│    - Extract properties using dataclasses.fields()              │
│    - Detect Optional[T] using typing.get_origin()               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Relationship Discovery                                       │
│    - Query: CALL db.relationshipTypes()                         │
│    - For each type: MATCH ()-[r:TYPE]->() RETURN keys(r)        │
│    - Aggregate unique property sets                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Validation Execution                                         │
│    - For each entity/property:                                  │
│      MATCH (n:Label)                                            │
│      COUNT where prop IS NOT NULL AND <> '' AND <> []           │
│    - Calculate percentages                                      │
│    - Categorize: FULL/PARTIAL/EMPTY                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Report Generation                                            │
│    - Console: Colored tables                                    │
│    - JSON: Structured data for automation                       │
│    - HTML: Interactive dashboard                                │
└─────────────────────────────────────────────────────────────────┘
```

## Empty Value Definition

A property is considered "empty" if it is:
- `NULL` (not set in Neo4j)
- Empty string: `''`
- Empty list: `[]`

This matches the filtering logic in `to_neo4j_properties()` methods.

## Legitimately Optional Properties

The following properties are expected to be optional (won't cause failures):

| Entity | Property | Reason |
|--------|----------|--------|
| Person | email | Some users don't have email addresses |
| PullRequest | merged_at | Only set for merged PRs |
| PullRequest | closed_at | Only set for closed PRs |
| Project | start_date, end_date | Not all projects have dates |
| Commit | fully_synced | Only set during incremental sync |
| All | url | Optional metadata field |

## Extending the Tests

### Adding New Assertions

To add custom validation logic, create a new test in [test_property_validation.py](test_property_validation.py):

```python
def test_custom_validation(validation_report):
    """Your custom validation logic."""
    for entity_type, results in validation_report.entity_results.items():
        # Your checks here
        pass
```

### Running Individual Modules

Each module can be run standalone for debugging:

```bash
# Test model introspection
python tests/property_validation/model_inspector.py

# Test relationship discovery (requires Neo4j)
python tests/property_validation/relationship_inspector.py

# Test query generation
python tests/property_validation/query_generator.py

# Run full validation
python tests/property_validation/validator.py
```

## Troubleshooting

### "No entity types discovered"
- Ensure `db/models.py` is in the Python path
- Check that dataclasses are properly decorated with `@dataclass`

### "Could not connect to Neo4j"
- Verify Neo4j is running: `docker compose ps`
- Check environment variables are set correctly
- Test connection: `cypher-shell -u neo4j -p <password>`

### "Property validation query failed"
- Check Neo4j logs for errors
- Verify indexes exist: `python scripts/create_indexes.py`
- Ensure constraints are created

### "HTML report not rendering properly"
- Check file permissions on `tests/property_validation/`
- Try opening directly in browser instead of file preview

## Future Enhancements

Potential improvements for future versions:

- [ ] Property type validation (string vs. int vs. date)
- [ ] Value constraint validation (e.g., email format, date ranges)
- [ ] Historical trend tracking (compare reports over time)
- [ ] Integration with CI/CD pipeline
- [ ] Slack/email notifications for failures
- [ ] Custom thresholds per property (e.g., "email should be >80% populated")
- [ ] Relationship property "required" detection based on usage patterns

## Related Documentation

- [db/models.py](../../db/models.py) - Entity dataclass definitions
- [design/high-level-design.md](../../design/high-level-design.md) - Overall graph design
- [design/RELATIONSHIPS_DESIGN.md](../../design/RELATIONSHIPS_DESIGN.md) - Relationship patterns
- [design/INDEX_STRATEGY.md](../../design/INDEX_STRATEGY.md) - Neo4j indexing strategy
