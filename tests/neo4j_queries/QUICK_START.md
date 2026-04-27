# Quick Start - Neo4j Query Tests

Get up and running in 2 minutes.

## Prerequisites
- Neo4j running (Docker or Desktop)
- Python 3.8+ with venv activated
- Database populated with simulation data

## 1. Install
```bash
pip install -r requirements_dev.txt
```

## 2. Run Tests
```bash
pytest tests/neo4j_queries/test_catalog_queries.py -v
```

## 3. View Results
- **Console**: Shown during test run
- **HTML**: `explorer.exe tests/neo4j_queries/results/latest.html`
- **JSON**: `cat tests/neo4j_queries/results/latest.json | jq`

## Common Commands
| Task | Command |
|------|---------|
| Run all tests | `pytest tests/neo4j_queries/ -v` |
| Run specific domain | `pytest tests/neo4j_queries/test_queries_github.py -v` |
| Run Person-to-Person | `pytest tests/neo4j_queries/test_queries_person_to_person.py -v` |
| Run single test | `pytest tests/neo4j_queries/test_queries_people.py::test_team_distribution -v` |
| Stop on first failure | `pytest tests/neo4j_queries/ -x` |

## Troubleshooting
| Problem | Solution |
|---------|----------|
| Database empty | `cd simulation && ./reload_all_simulations.sh` |
| Connection error | Check Neo4j is running: `docker ps \| grep neo4j` |
| Module not found | `pip install pytest-html pyyaml` |
| Slow queries | Run `python scripts/create_indexes.py` |

## Next Steps
- See [README.md](README.md) for full documentation
- Edit `queries_config.yaml` to customize expectations
- Browse test files (`test_queries_*.py`) to see all available queries
