"""
Discover relationship types and their properties from Neo4j database.
"""

from typing import Dict, List, Set
from neo4j import Session


def discover_relationship_types(session: Session) -> List[str]:
    """
    Discover all relationship types in the Neo4j database.
    
    Args:
        session: Neo4j session
        
    Returns:
        List of relationship type names
    """
    query = "CALL db.relationshipTypes()"
    result = session.run(query)
    
    rel_types = [record["relationshipType"] for record in result]
    return sorted(rel_types)


def discover_relationship_properties(session: Session, rel_type: str) -> List[str]:
    """
    Discover properties for a specific relationship type.
    
    Args:
        session: Neo4j session
        rel_type: The relationship type to inspect
        
    Returns:
        List of property names found on this relationship type
    """
    # Sample relationships to find all possible properties
    # We use LIMIT to avoid scanning the entire database
    query = f"""
    MATCH ()-[r:`{rel_type}`]->()
    WITH r LIMIT 1000
    UNWIND keys(r) as key
    RETURN DISTINCT key
    ORDER BY key
    """
    
    try:
        result = session.run(query)
        properties = [record["key"] for record in result]
        return properties
    except Exception as e:
        print(f"Warning: Could not discover properties for relationship type '{rel_type}': {e}")
        return []


def discover_all_relationships(session: Session) -> Dict[str, List[str]]:
    """
    Discover all relationship types and their properties.
    
    Args:
        session: Neo4j session
        
    Returns:
        Dictionary mapping relationship type to list of property names
        (empty list if relationship has no properties)
    """
    rel_types = discover_relationship_types(session)
    
    relationship_metadata = {}
    for rel_type in rel_types:
        properties = discover_relationship_properties(session, rel_type)
        # Include ALL relationships, even those without properties
        relationship_metadata[rel_type] = properties
    
    return relationship_metadata


def print_discovered_relationships(relationships: Dict[str, List[str]]) -> None:
    """
    Print discovered relationships in a readable format.
    
    Args:
        relationships: Dictionary of relationship types and their properties
    """
    print(f"\n{'='*80}")
    print(f"DISCOVERED RELATIONSHIPS FROM NEO4J")
    print(f"{'='*80}\n")
    
    for rel_type, properties in sorted(relationships.items()):
        print(f"Relationship: {rel_type}")
        if properties:
            print(f"  Properties ({len(properties)}):")
            for prop in properties:
                print(f"    - {prop} [OPTIONAL]")  # All relationship properties treated as optional
        else:
            print(f"  No properties")
        print()


if __name__ == "__main__":
    # Test the discovery function (requires Neo4j connection)
    import os
    from neo4j import GraphDatabase
    
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(username, password))
    
    try:
        with driver.session() as session:
            relationships = discover_all_relationships(session)
            print_discovered_relationships(relationships)
            print(f"Total relationship types with properties: {len(relationships)}")
    finally:
        driver.close()
