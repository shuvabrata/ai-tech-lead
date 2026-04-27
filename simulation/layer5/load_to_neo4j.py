"""
Load Git Repositories into Neo4j.
This loads Layer 5 of the graph: Repository nodes and COLLABORATOR relationships.

Key differences from previous layers:
- COLLABORATOR relationships have properties (permission, granted_at, role, reason)
- Repository nodes have an array field (topics)
- Follows the same pattern: merge nodes one at a time, caller may/may not have relationships
"""

import json
import os

from neo4j import GraphDatabase
from connectors.db.models import Repository, Relationship, merge_repository, merge_relationship, create_constraints


def load_repositories_to_neo4j():
    """Load Repository nodes into Neo4j."""
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer5_repositories.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Create constraints for Layer 5
            create_constraints(session, layers=[5])
            
            # Load repositories one at a time
            repositories = data['nodes']['repositories']
            for repo_data in repositories:
                # Create Repository object (no relationships embedded)
                repository = Repository(
                    id=repo_data['id'],
                    name=repo_data['name'],
                    full_name=repo_data['full_name'],
                    url=repo_data['url'],
                    language=repo_data['language'],
                    is_private=repo_data['is_private'],
                    topics=repo_data['topics'],
                    created_at=repo_data['created_at'],
                    _last_synced_at=repo_data.get('_last_synced_at')
                )
                
                # Merge repository (without relationships for now)
                merge_repository(session, repository)
            
            print(f"✓ Loaded {len(repositories)} repositories")
    
    finally:
        driver.close()


def load_relationships():
    """Load all COLLABORATOR relationships.
    
    Note: Relationships have properties like permission, granted_at, role, reason.
    """
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer5_repositories.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Process relationships one at a time
            relationship_count = 0
            for rel_data in data['relationships']:
                # Create Relationship object with properties
                relationship = Relationship(
                    type=rel_data['type'],
                    from_id=rel_data['from_id'],
                    to_id=rel_data['to_id'],
                    from_type=rel_data['from_type'],
                    to_type=rel_data['to_type'],
                    properties=rel_data.get('properties', {})
                )
                
                # Merge relationship (handles directionality automatically)
                merge_relationship(session, relationship)
                relationship_count += 1
            
            print(f"✓ Loaded {relationship_count} COLLABORATOR relationships")
    
    finally:
        driver.close()


def validate_layer5():
    """Run validation queries to verify Layer 5 data."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            print("\n" + "=" * 60)
            print("LAYER 5 VALIDATION")
            print("=" * 60)
            
            # 1. Repository count
            result = session.run("MATCH (r:Repository) RETURN count(r) as count")
            count = result.single()['count']
            print(f"\n1. Total Repositories: {count}")
            
            # 2. Repository collaborators by team (WRITE access)
            print("\n2. Repository WRITE Access by Team:")
            result = session.run("""
                MATCH (t:Team)-[c:COLLABORATOR]-(r:Repository)
                WHERE c.permission = 'WRITE'
                RETURN t.name as team, collect(r.name) as repositories
                ORDER BY team
            """)
            for record in result:
                print(f"   {record['team']}: {', '.join(record['repositories'])}")
            
            # 3. Repository maintainers (individuals with WRITE access)
            print("\n3. Repository Maintainers (Individual WRITE Access):")
            result = session.run("""
                MATCH (p:Person)-[c:COLLABORATOR]-(r:Repository)
                WHERE c.permission = 'WRITE'
                RETURN r.name as repository, 
                       collect(p.name) as maintainers
                ORDER BY repository
            """)
            for record in result:
                print(f"   {record['repository']}: {', '.join(record['maintainers'])}")
            
            # 4. Cross-team access (teams with READ permission)
            print("\n4. Cross-Team READ Access:")
            result = session.run("""
                MATCH (t:Team)-[c:COLLABORATOR]-(r:Repository)
                WHERE c.permission = 'READ'
                RETURN r.name as repository, 
                       collect(t.name) as teams_with_read_access
                ORDER BY repository
            """)
            for record in result:
                if record['teams_with_read_access']:
                    print(f"   {record['repository']}: {', '.join(record['teams_with_read_access'])}")
            
            # 5. Permission summary per repository
            print("\n5. Permission Summary per Repository:")
            result = session.run("""
                MATCH (r:Repository)-[c:COLLABORATOR]-(collaborator)
                RETURN r.name as repository,
                       sum(CASE WHEN c.permission = 'WRITE' THEN 1 ELSE 0 END) as write_access,
                       sum(CASE WHEN c.permission = 'READ' THEN 1 ELSE 0 END) as read_access,
                       count(collaborator) as total_collaborators
                ORDER BY repository
            """)
            for record in result:
                print(f"   {record['repository']}: "
                      f"WRITE={record['write_access']}, "
                      f"READ={record['read_access']}, "
                      f"Total={record['total_collaborators']}")
            
            # 6. COLLABORATOR relationship count
            print("\n6. COLLABORATOR Relationship Count:")
            result = session.run("MATCH ()-[r:COLLABORATOR]-() RETURN count(r) as rel_count")
            count = result.single()['rel_count']
            print(f"   ✓ {count} COLLABORATOR relationships (undirected)")
            
            print("\n" + "=" * 60)
    
    finally:
        driver.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Loading Layer 5: Git Repositories")
    print("=" * 60)
    
    load_repositories_to_neo4j()
    load_relationships()
    validate_layer5()
    
    print("\n✓ Layer 5 loading complete!")
