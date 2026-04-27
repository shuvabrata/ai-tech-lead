"""
Load Git Branches into Neo4j.
This loads Layer 6 of the graph: Branch nodes and BRANCH_OF relationships.

Key differences from previous layers:
- Branch nodes have datetime field (last_commit_timestamp)
- BRANCH_OF relationships are simple (no properties)
- Follows the same pattern: merge nodes one at a time, caller may/may not have relationships
- Note: We do not track branch created_at due to performance overhead (see new_branch_handler.py)
"""

import json
import os

from neo4j import GraphDatabase
from connectors.db.models import Branch, Relationship, merge_branch, merge_relationship, create_constraints


def load_branches_to_neo4j():
    """Load Branch nodes into Neo4j."""
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer6_branches.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Create constraints for Layer 6
            create_constraints(session, layers=[6])
            
            # Load branches one at a time
            branches = data['nodes']['branches']
            for branch_data in branches:
                # Create Branch object (no relationships embedded)
                branch = Branch(
                    id=branch_data['id'],
                    name=branch_data['name'],
                    is_default=branch_data['is_default'],
                    is_protected=branch_data['is_protected'],
                    is_deleted=branch_data['is_deleted'],
                    is_external=branch_data.get('is_external', False), 
                    last_commit_sha=branch_data['last_commit_sha'],
                    last_commit_timestamp=branch_data['last_commit_timestamp']
                )
                
                # Merge branch (without relationships for now)
                merge_branch(session, branch)
            
            print(f"✓ Loaded {len(branches)} branches")
    
    finally:
        driver.close()


def load_relationships():
    """Load all BRANCH_OF relationships."""
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer6_branches.json')
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
                # Create Relationship object (no properties for BRANCH_OF)
                relationship = Relationship(
                    type=rel_data['type'],
                    from_id=rel_data['from_id'],
                    to_id=rel_data['to_id'],
                    from_type=rel_data['from_type'],
                    to_type=rel_data['to_type']
                )
                
                # Merge relationship (handles directionality automatically)
                merge_relationship(session, relationship)
                relationship_count += 1
            
            print(f"✓ Loaded {relationship_count} BRANCH_OF relationships")
    
    finally:
        driver.close()


def validate_layer6():
    """Run validation queries to verify Layer 6 data."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            print("\n" + "=" * 60)
            print("LAYER 6 VALIDATION")
            print("=" * 60)
            
            # 1. Total branches
            result = session.run("MATCH (b:Branch) RETURN count(b) as count")
            count = result.single()['count']
            print(f"\n1. Total Branches: {count}")
            
            # 2. Branches per repository
            print("\n2. Total Branches per Repository:")
            result = session.run("""
                MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
                RETURN r.name, 
                       count(b) as total_branches,
                       sum(CASE WHEN b.is_default THEN 1 ELSE 0 END) as default_branches,
                       sum(CASE WHEN b.is_deleted THEN 1 ELSE 0 END) as deleted_branches
                ORDER BY total_branches DESC
            """)
            for record in result:
                print(f"   {record['r.name']}: {record['total_branches']} total "
                      f"(default: {record['default_branches']}, deleted: {record['deleted_branches']})")
            
            # 3. Active branches (non-default, not deleted)
            print("\n3. Active Branches per Repository:")
            result = session.run("""
                MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
                WHERE b.is_default = false AND NOT b.is_deleted
                RETURN r.name, count(b) as active_branches
                ORDER BY active_branches DESC
            """)
            for record in result:
                print(f"   {record['r.name']}: {record['active_branches']} active branches")
            
            # 4. Stale branches (> 30 days old)
            print("\n4. Stale Branches (last commit > 30 days ago):")
            result = session.run("""
                MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
                WHERE b.last_commit_timestamp < datetime() - duration({days: 30})
                  AND b.is_default = false
                  AND NOT b.is_deleted
                RETURN b.name, r.name as repo, b.last_commit_timestamp,
                       duration.between(b.last_commit_timestamp, datetime()).days as days_old
                ORDER BY days_old DESC
                LIMIT 10
            """)
            stale_count = 0
            for record in result:
                stale_count += 1
                print(f"   {record['b.name']} ({record['repo']}): {record['days_old']} days old")
            
            if stale_count == 0:
                print("   (No stale branches found)")
            
            # 5. Protected branches
            print("\n5. Protected Branches:")
            result = session.run("""
                MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
                WHERE b.is_protected
                RETURN r.name, collect(b.name) as protected_branches
                ORDER BY r.name
            """)
            for record in result:
                print(f"   {record['r.name']}: {', '.join(record['protected_branches'])}")
            
            # 6. BRANCH_OF relationship count
            print("\n6. BRANCH_OF Relationship Count:")
            result = session.run("MATCH ()-[r:BRANCH_OF]-() RETURN count(r) as rel_count")
            count = result.single()['rel_count']
            print(f"   ✓ {count} BRANCH_OF relationships (undirected)")
            
            print("\n" + "=" * 60)
    
    finally:
        driver.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Loading Layer 6: Git Branches")
    print("=" * 60)
    
    load_branches_to_neo4j()
    load_relationships()
    validate_layer6()
    
    print("\n✓ Layer 6 loading complete!")
