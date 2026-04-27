"""
Execute property validation against Neo4j database.
"""

from datetime import datetime
from typing import Dict, List
from neo4j import Session

from tests.property_validation.models import (
    PropertyValidationResult,
    ValidationReport,
    PopulationCategory,
    EntityMetadata,
    RelationshipExistenceResult,
    RelationshipCoverageResult
)
from tests.property_validation.model_inspector import discover_entity_types
from tests.property_validation.relationship_inspector import discover_all_relationships
from tests.property_validation.code_relationship_inspector import (
    get_all_relationship_names,
    get_relationship_pair,
    is_bidirectional,
    is_same_name_bidirectional
)
from tests.property_validation.query_generator import (
    generate_node_property_query,
    generate_relationship_property_query
)


class PropertyValidator:
    """Validates property population across Neo4j nodes and relationships."""
    
    def __init__(self, session: Session):
        """
        Initialize the validator.
        
        Args:
            session: Neo4j session to use for queries
        """
        self.session = session
        self.entity_metadata: Dict[str, EntityMetadata] = {}
        self.relationship_metadata: Dict[str, List[str]] = {}
    
    def categorize_result(self, populated_count: int, total_count: int) -> PopulationCategory:
        """
        Categorize a validation result based on population percentage.
        
        Args:
            populated_count: Number of entities with property populated
            total_count: Total number of entities
            
        Returns:
            PopulationCategory (FULL, PARTIAL, or EMPTY)
        """
        if total_count == 0:
            return PopulationCategory.EMPTY
        
        percentage = (populated_count / total_count) * 100
        
        if percentage == 100.0:
            return PopulationCategory.FULL
        elif percentage > 0:
            return PopulationCategory.PARTIAL
        else:
            return PopulationCategory.EMPTY
    
    def validate_entity(self, entity_name: str, metadata: EntityMetadata) -> List[PropertyValidationResult]:
        """
        Validate all properties for a specific entity type.
        
        Args:
            entity_name: The name of the entity (e.g., "Person")
            metadata: Metadata about the entity's properties
            
        Returns:
            List of PropertyValidationResult objects
        """
        results = []
        
        for prop in metadata.properties:
            query = generate_node_property_query(entity_name, prop.name)
            
            try:
                result = self.session.run(query)
                record = result.single()
                
                if record:
                    total = record["total"]
                    populated = record["populated"]
                    empty = record["empty"]
                    
                    if total > 0:
                        percentage = (populated / total) * 100
                    else:
                        percentage = 0.0
                    
                    category = self.categorize_result(populated, total)
                    
                    results.append(PropertyValidationResult(
                        property_name=prop.name,
                        entity_or_rel_type=entity_name,
                        total_count=total,
                        populated_count=populated,
                        empty_count=empty,
                        population_percentage=percentage,
                        category=category,
                        is_required=not prop.is_optional
                    ))
            except Exception as e:
                print(f"Error validating {entity_name}.{prop.name}: {e}")
                # Create a failed result
                results.append(PropertyValidationResult(
                    property_name=prop.name,
                    entity_or_rel_type=entity_name,
                    total_count=0,
                    populated_count=0,
                    empty_count=0,
                    population_percentage=0.0,
                    category=PopulationCategory.EMPTY,
                    is_required=not prop.is_optional
                ))
        
        return results
    
    def validate_relationship(self, rel_type: str, properties: List[str]) -> List[PropertyValidationResult]:
        """
        Validate all properties for a specific relationship type.
        
        Args:
            rel_type: The relationship type (e.g., "COLLABORATOR")
            properties: List of property names to validate
            
        Returns:
            List of PropertyValidationResult objects
        """
        results = []
        
        for prop_name in properties:
            query = generate_relationship_property_query(rel_type, prop_name)
            
            try:
                result = self.session.run(query)
                record = result.single()
                
                if record:
                    total = record["total"]
                    populated = record["populated"]
                    empty = record["empty"]
                    
                    if total > 0:
                        percentage = (populated / total) * 100
                    else:
                        percentage = 0.0
                    
                    category = self.categorize_result(populated, total)
                    
                    results.append(PropertyValidationResult(
                        property_name=prop_name,
                        entity_or_rel_type=rel_type,
                        total_count=total,
                        populated_count=populated,
                        empty_count=empty,
                        population_percentage=percentage,
                        category=category,
                        is_required=False  # All relationship properties treated as optional
                    ))
            except Exception as e:
                print(f"Error validating relationship {rel_type}.{prop_name}: {e}")
                results.append(PropertyValidationResult(
                    property_name=prop_name,
                    entity_or_rel_type=rel_type,
                    total_count=0,
                    populated_count=0,
                    empty_count=0,
                    population_percentage=0.0,
                    category=PopulationCategory.EMPTY,
                    is_required=False
                ))
        
        return results
    
    def validate_relationship_existence(self, rel_type: str, has_properties: bool) -> RelationshipExistenceResult:
        """
        Validate relationship existence and bidirectional consistency.
        
        Args:
            rel_type: The relationship type
            has_properties: Whether this relationship has properties
            
        Returns:
            RelationshipExistenceResult with counts and consistency info
        """
        # Get count of this relationship
        count_query = f"""
        MATCH ()-[r:`{rel_type}`]->()
        RETURN count(r) as count
        """
        
        try:
            result = self.session.run(count_query)
            record = result.single()
            total_count = record["count"] if record else 0
        except Exception as e:
            print(f"  Warning: Could not count {rel_type}: {e}")
            total_count = 0
        
        # Check if this relationship is expected (defined in code)
        all_expected = get_all_relationship_names()
        is_expected = rel_type in all_expected
        
        # Check bidirectional info
        is_bidir = is_bidirectional(rel_type)
        is_same_name = is_same_name_bidirectional(rel_type)
        reverse_rel = get_relationship_pair(rel_type)
        
        # Get reverse count if bidirectional
        reverse_count = None
        count_discrepancy = None
        
        if is_bidir and reverse_rel and reverse_rel != rel_type:
            # Different-name bidirectional - check reverse exists
            reverse_query = f"""
            MATCH ()-[r:`{reverse_rel}`]->()
            RETURN count(r) as count
            """
            try:
                result = self.session.run(reverse_query)
                record = result.single()
                reverse_count = record["count"] if record else 0
                count_discrepancy = abs(total_count - reverse_count)
            except Exception:
                reverse_count = 0
                count_discrepancy = total_count
        
        return RelationshipExistenceResult(
            rel_type=rel_type,
            total_count=total_count,
            has_properties=has_properties,
            is_expected=is_expected,
            is_bidirectional=is_bidir,
            is_same_name_bidirectional=is_same_name,
            reverse_rel_type=reverse_rel if reverse_rel != rel_type else None,
            reverse_count=reverse_count,
            count_discrepancy=count_discrepancy
        )
    
    def validate_relationship_coverage(self, discovered_rels: List[str]) -> RelationshipCoverageResult:
        """
        Validate relationship coverage against expected definitions.
        
        Args:
            discovered_rels: List of relationship types found in Neo4j
            
        Returns:
            RelationshipCoverageResult with coverage analysis
        """
        expected_rels = get_all_relationship_names()
        discovered_set = set(discovered_rels)
        expected_set = set(expected_rels)
        
        missing = list(expected_set - discovered_set)
        unexpected = list(discovered_set - expected_set)
        
        # Check for bidirectional mismatches
        mismatches = []
        for rel_type in discovered_rels:
            if is_bidirectional(rel_type):
                reverse_rel = get_relationship_pair(rel_type)
                if reverse_rel and reverse_rel != rel_type:
                    # Different-name bidirectional - check if reverse exists
                    if reverse_rel not in discovered_set:
                        mismatches.append(f"{rel_type} exists but reverse {reverse_rel} is missing")
        
        return RelationshipCoverageResult(
            expected_count=len(expected_rels),
            discovered_count=len(discovered_rels),
            missing_relationships=sorted(missing),
            unexpected_relationships=sorted(unexpected),
            bidirectional_mismatches=mismatches
        )
    
    def validate_all(self) -> ValidationReport:
        """
        Validate all entities and relationships.
        
        Returns:
            ValidationReport containing all validation results
        """
        print("Discovering entity types from db/models.py...")
        self.entity_metadata = discover_entity_types()
        print(f"Found {len(self.entity_metadata)} entity types")
        
        print("\nDiscovering relationship types from Neo4j...")
        self.relationship_metadata = discover_all_relationships(self.session)
        print(f"Found {len(self.relationship_metadata)} relationship types (including those without properties)")
        
        entity_results: Dict[str, List[PropertyValidationResult]] = {}
        relationship_results: Dict[str, List[PropertyValidationResult]] = {}
        relationship_existence: Dict[str, RelationshipExistenceResult] = {}
        
        # Validate entities
        print("\nValidating entity properties...")
        for entity_name, metadata in self.entity_metadata.items():
            print(f"  Validating {entity_name}...")
            results = self.validate_entity(entity_name, metadata)
            entity_results[entity_name] = results
        
        # Validate relationships (property population)
        print("\nValidating relationship properties...")
        for rel_type, properties in self.relationship_metadata.items():
            if properties:  # Only validate properties if they exist
                print(f"  Validating {rel_type} properties...")
                results = self.validate_relationship(rel_type, properties)
                relationship_results[rel_type] = results
        
        # Validate relationship existence and consistency
        print("\nValidating relationship existence and consistency...")
        for rel_type, properties in self.relationship_metadata.items():
            print(f"  Checking {rel_type}...")
            existence_result = self.validate_relationship_existence(rel_type, len(properties) > 0)
            relationship_existence[rel_type] = existence_result
        
        # Validate relationship coverage
        print("\nValidating relationship coverage against expected definitions...")
        coverage = self.validate_relationship_coverage(list(self.relationship_metadata.keys()))
        
        # Count failures (required properties with 0% population)
        failure_count = 0
        for results in entity_results.values():
            for result in results:
                if result.is_required and result.category == PopulationCategory.EMPTY:
                    failure_count += 1
        
        return ValidationReport(
            timestamp=datetime.now(),
            entity_results=entity_results,
            relationship_results=relationship_results,
            relationship_existence=relationship_existence,
            relationship_coverage=coverage,
            failure_count=failure_count
        )


if __name__ == "__main__":
    # Test validation
    import os
    from neo4j import GraphDatabase
    
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    try:
        with driver.session() as session:
            validator = PropertyValidator(session)
            report = validator.validate_all()
            print(f"\nValidation complete!")
            print(f"Failures: {report.failure_count}")
    finally:
        driver.close()
