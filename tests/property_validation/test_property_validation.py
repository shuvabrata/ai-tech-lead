
import pytest
pytest.skip("Skipping all tests in this file (marked as skipped by request)", allow_module_level=True)

"""
Test suite for Neo4j property validation.

This test validates that all nodes and relationships in Neo4j have their properties
populated according to the dataclass definitions in db/models.py.

The test dynamically discovers entity types and properties from the codebase,
so it automatically adapts as models evolve.

Usage:
    pytest tests/property_validation/test_property_validation.py -v -s

Environment variables required:
    NEO4J_URI - Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USERNAME - Neo4j username (default: neo4j)
    NEO4J_PASSWORD - Neo4j password (required)
"""

import os
import pytest
from pathlib import Path
from neo4j import GraphDatabase

from tests.property_validation.validator import PropertyValidator
from tests.property_validation.report_generator import (
    generate_console_report,
    generate_json_report,
    generate_html_report
)


@pytest.fixture(scope="module")
def neo4j_driver():
    """Create Neo4j driver for the test session."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD')
    
    if not password:
        pytest.skip("NEO4J_PASSWORD environment variable not set")
    
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    # Verify connection
    try:
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Could not connect to Neo4j: {e}")
    
    yield driver
    
    driver.close()


@pytest.fixture(scope="module")
def validation_report(neo4j_driver):
    """Run validation once and reuse the report for all tests."""
    with neo4j_driver.session() as session:
        validator = PropertyValidator(session)
        report = validator.validate_all()
        return report


def test_validate_all_properties(validation_report):
    """
    Validate that all required properties are populated in at least some nodes.
    
    This test fails if ANY required property has 0% population across all nodes.
    """
    failures = []
    
    # Check entity properties
    for entity_type, results in validation_report.entity_results.items():
        for result in results:
            if result.is_required and result.population_percentage == 0.0:
                failures.append(
                    f"{entity_type}.{result.property_name}: REQUIRED property is empty in all {result.total_count} nodes"
                )
    
    # Build failure message
    if failures:
        failure_msg = f"\n\n{len(failures)} required properties are completely empty:\n"
        for failure in failures:
            failure_msg += f"  ❌ {failure}\n"
        pytest.fail(failure_msg)
    
    # If no failures, report success
    summary = validation_report._generate_summary()
    print(f"\n✓ All required properties have at least some population")
    print(f"  Total properties validated: {summary['total_properties_validated']}")
    print(f"  Full population: {summary['full_population']}")
    print(f"  Partial population: {summary['partial_population']}")
    print(f"  Empty (optional only): {summary['empty_population']}")


def test_generate_reports(validation_report):
    """
    Generate console, JSON, and HTML reports.
    """
    # Console report
    print("\n" + "="*100)
    print("GENERATING REPORTS")
    print("="*100)
    generate_console_report(validation_report)
    
    # JSON report
    report_dir = Path(__file__).parent / "results"
    report_dir.mkdir(exist_ok=True)
    json_path = report_dir / "report.json"
    generate_json_report(validation_report, json_path)
    
    # HTML report
    html_path = report_dir / "report.html"
    generate_html_report(validation_report, html_path)
    
    # Verify files were created
    assert json_path.exists(), f"JSON report not created at {json_path}"
    assert html_path.exists(), f"HTML report not created at {html_path}"
    
    print(f"\n✓ All reports generated successfully")


def test_no_entity_types_missed(validation_report):
    """
    Verify that we discovered a reasonable number of entity types.
    
    This is a sanity check to ensure the model introspection is working.
    """
    entity_count = len(validation_report.entity_results)
    
    # We expect at least 10 entity types (Person, Team, Repository, Issue, etc.)
    assert entity_count >= 10, (
        f"Only discovered {entity_count} entity types. "
        "Expected at least 10. Model introspection may have failed."
    )
    
    print(f"\n✓ Discovered {entity_count} entity types from db/models.py")


def test_partial_population_warning(validation_report):
    """
    Warn about required properties with partial population.
    
    This test does not fail, but prints warnings for required properties
    that are not 100% populated.
    """
    warnings = []
    
    for entity_type, results in validation_report.entity_results.items():
        for result in results:
            if result.is_required and 0 < result.population_percentage < 100.0:
                warnings.append(
                    f"{entity_type}.{result.property_name}: "
                    f"{result.population_percentage:.1f}% populated "
                    f"({result.empty_count}/{result.total_count} nodes missing)"
                )
    
    if warnings:
        print(f"\n⚠️  {len(warnings)} required properties have partial population:")
        for warning in warnings[:10]:  # Show first 10
            print(f"  {warning}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")
    else:
        print(f"\n✓ All required properties are 100% populated")


def test_all_expected_relationships_exist(validation_report):
    """
    Verify that all expected relationships from model definitions exist in database.
    """
    if not validation_report.relationship_coverage:
        pytest.skip("Relationship coverage validation not available")
    
    coverage = validation_report.relationship_coverage
    
    if coverage.missing_relationships:
        failure_msg = f"\n\n{len(coverage.missing_relationships)} expected relationships are MISSING from the database:\n"
        for rel in coverage.missing_relationships:
            failure_msg += f"  ✗ {rel}\n"
        pytest.fail(failure_msg)
    
    print(f"\n✓ All {coverage.expected_count} expected relationships exist in database")


def test_no_unexpected_relationships(validation_report):
    """
    Verify that there are no unexpected relationship types in the database.
    
    This test warns about relationships not defined in the model relationship definitions.
    """
    if not validation_report.relationship_coverage:
        pytest.skip("Relationship coverage validation not available")
    
    coverage = validation_report.relationship_coverage
    
    if coverage.unexpected_relationships:
        print(f"\n⚠️  {len(coverage.unexpected_relationships)} unexpected relationships found:")
        for rel in coverage.unexpected_relationships:
            print(f"  ? {rel}")
        print("\nThese should be added to the relationship definitions in db/models.py")
    else:
        print(f"\n✓ No unexpected relationships")


def test_bidirectional_consistency(validation_report):
    """
    Verify directional relationship pairs have consistent counts in both directions.
    """
    if not validation_report.relationship_existence:
        pytest.skip("Relationship existence validation not available")
    
    inconsistencies = []
    
    for rel_type, result in validation_report.relationship_existence.items():
        if result.is_bidirectional and not result.is_same_name_bidirectional:
            if result.count_discrepancy and result.count_discrepancy > 10:
                inconsistencies.append(
                    f"{rel_type} ↔ {result.reverse_rel_type}: "
                    f"{result.total_count} vs {result.reverse_count} "
                    f"(difference: {result.count_discrepancy})"
                )
    
    if inconsistencies:
        print(f"\n⚠️  {len(inconsistencies)} directional relationships have significant count discrepancies:")
        for inc in inconsistencies[:10]:
            print(f"  {inc}")
        if len(inconsistencies) > 10:
            print(f"  ... and {len(inconsistencies) - 10} more")
    else:
        print(f"\n✓ All directional relationships are consistent")


def test_relationship_coverage_summary(validation_report):
    """
    Display comprehensive relationship coverage summary.
    """
    if not validation_report.relationship_coverage:
        pytest.skip("Relationship coverage validation not available")
    
    coverage = validation_report.relationship_coverage
    
    print(f"\n{'='*80}")
    print(f"RELATIONSHIP COVERAGE SUMMARY")
    print(f"{'='*80}")
    print(f"Expected relationships: {coverage.expected_count}")
    print(f"Discovered relationships: {coverage.discovered_count}")
    print(f"Coverage: {(coverage.discovered_count/coverage.expected_count*100):.1f}%")
    print(f"Missing: {len(coverage.missing_relationships)}")
    print(f"Unexpected: {len(coverage.unexpected_relationships)}")
    print(f"Bidirectional mismatches: {len(coverage.bidirectional_mismatches)}")
    print(f"{'='*80}")


if __name__ == "__main__":
    # Allow running directly for quick testing
    pytest.main([__file__, "-v", "-s"])
