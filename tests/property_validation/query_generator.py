"""
Generate Cypher queries for property validation.
"""


def generate_node_property_query(label: str, property_name: str) -> str:
    """
    Generate a Cypher query to validate property population for nodes.
    
    The query counts:
    - Total nodes with this label
    - Nodes where the property is populated (not null, not empty string, not empty list)
    
    Args:
        label: The node label (e.g., "Person", "Repository")
        property_name: The property to validate
        
    Returns:
        Cypher query string
    """
    query = f"""
    MATCH (n:`{label}`)
    WITH count(n) as total
    MATCH (n:`{label}`)
    WITH total, n.`{property_name}` as prop
    WITH total,
         count(CASE 
             WHEN prop IS NOT NULL 
             AND prop <> '' 
             AND prop <> []
             THEN 1 
         END) as populated
    RETURN total, populated, (total - populated) as empty
    """
    return query.strip()


def generate_relationship_property_query(rel_type: str, property_name: str) -> str:
    """
    Generate a Cypher query to validate property population for relationships.
    
    The query counts:
    - Total relationships of this type
    - Relationships where the property is populated (not null, not empty string, not empty list)
    
    Args:
        rel_type: The relationship type (e.g., "COLLABORATOR", "MODIFIES")
        property_name: The property to validate
        
    Returns:
        Cypher query string
    """
    query = f"""
    MATCH ()-[r:`{rel_type}`]->()
    WITH count(r) as total
    MATCH ()-[r:`{rel_type}`]->()
    WITH total, r.`{property_name}` as prop
    WITH total,
         count(CASE 
             WHEN prop IS NOT NULL 
             AND prop <> '' 
             AND prop <> []
             THEN 1 
         END) as populated
    RETURN total, populated, (total - populated) as empty
    """
    return query.strip()


if __name__ == "__main__":
    # Test query generation
    print("Node property query example:")
    print(generate_node_property_query("Person", "email"))
    print("\n" + "="*80 + "\n")
    print("Relationship property query example:")
    print(generate_relationship_property_query("COLLABORATOR", "permission"))
