"""
Pytest configuration and fixtures for Neo4j query testing.
"""

import os
import pytest
import yaml
from pathlib import Path
from neo4j import GraphDatabase

from helpers.query_executor import QueryExecutor
from helpers.report_generator import ReportGenerator
from helpers.models import QueryExpectation


# Global list to collect all query results during test session
query_results = []


@pytest.fixture(scope="session")
def config():
    """Load test configuration from queries_config.yaml."""
    config_file = Path(__file__).parent / "queries_config.yaml"
    
    if config_file.exists():
        with open(config_file) as f:
            return yaml.safe_load(f)
    return {"queries": []}


@pytest.fixture(scope="session")
def expectations(config):
    """Build expectations lookup from config."""
    exp_map = {}
    for query_config in config.get("queries", []):
        exp_data = query_config.get("expectations", {})
        exp_map[query_config["name"]] = QueryExpectation(
            min_rows=exp_data.get("min_rows"),
            max_rows=exp_data.get("max_rows"),
            max_time_ms=exp_data.get("max_time_ms"),
            required_columns=exp_data.get("required_columns"),
            allow_empty_columns=exp_data.get("allow_empty_columns", True)
        )
    return exp_map


@pytest.fixture(scope="session")
def neo4j_driver():
    """
    Create Neo4j driver for entire test session.
    Uses environment variables for connection.
    """
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password123')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    # Verify connection
    try:
        driver.verify_connectivity()
    except Exception as e:
        pytest.fail(f"Cannot connect to Neo4j at {uri}: {str(e)}")
    
    yield driver
    driver.close()


@pytest.fixture(scope="function")
def neo4j_session(neo4j_driver):
    """Create a new Neo4j session for each test."""
    session = neo4j_driver.session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def query_executor(neo4j_session):
    """Create query executor for each test."""
    return QueryExecutor(neo4j_session)


@pytest.fixture(scope="function")
def track_result():
    """
    Fixture to track query results.
    Tests call this to register their results.
    """
    def tracker(result):
        query_results.append(result)
    return tracker


@pytest.fixture(scope="session", autouse=True)
def ensure_neo4j_data(neo4j_driver):
    """
    Verify that Neo4j has data before running tests.
    This runs once at the start of the test session.
    """
    with neo4j_driver.session() as session:
        result = session.run("MATCH (n) RETURN count(n) as count")
        count = result.single()['count']
        
        if count == 0:
            pytest.exit(
                "No data in Neo4j database. "
                "Please load data before running tests. "
                "For simulation data, run: cd simulation && ./reload_all_simulations.sh"
            )


def pytest_sessionfinish(session, exitstatus):
    """
    Generate reports after all tests complete.
    This hook is called by pytest automatically.
    """
    if not query_results:
        return
    
    print("\n\n" + "=" * 80)
    print(" Generating Test Reports".center(80))
    print("=" * 80)
    
    generator = ReportGenerator()
    
    # Generate JSON report
    json_file = generator.generate_json_report(query_results)
    print(f"✅ JSON report: {json_file}")
    
    # Generate HTML report
    html_file = generator.generate_html_report(query_results)
    print(f"✅ HTML report: {html_file}")
    
    # Print console report
    console_report = generator.generate_console_report(query_results)
    print(console_report)
    
    # Also save console report as text file
    text_file = generator.results_dir / "latest.txt"
    with open(text_file, 'w') as f:
        f.write(console_report)
    print(f"✅ Text report: {text_file}")
