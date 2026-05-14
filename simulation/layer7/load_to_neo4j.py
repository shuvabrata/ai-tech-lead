"""
Load Git Commits & Files into Neo4j.
This loads Layer 7 of the graph: Commit and File nodes with their relationships.

Key differences from previous layers:
- Two node types: Commit and File
- MODIFIES relationships have properties (additions, deletions)
- Multiple relationship types: PART_OF, AUTHORED_BY, MODIFIES, REFERENCES
- Follows the same pattern: merge nodes one at a time, caller may/may not have relationships
"""

import json
import os

from neo4j import GraphDatabase
from connectors.neo4j_db.models import Commit, File, Relationship, merge_commit, merge_file, merge_relationship, create_constraints


def load_commits_to_neo4j():
    """Load Commit nodes into Neo4j."""
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer7_commits.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Create constraints for Layer 7
            create_constraints(session, layers=[7])
            
            # Load commits one at a time
            commits = data['nodes']['commits']
            for commit_data in commits:
                # Create Commit object (no relationships embedded)
                commit = Commit(
                    id=commit_data['id'],
                    sha=commit_data['sha'],
                    message=commit_data['message'],
                    created_at=commit_data['created_at'],
                    additions=commit_data['additions'],
                    deletions=commit_data['deletions'],
                    files_changed=commit_data['files_changed']
                )
                
                # Merge commit (without relationships for now)
                merge_commit(session, commit)
            
            print(f"✓ Loaded {len(commits)} commits")
    
    finally:
        driver.close()


def load_files_to_neo4j():
    """Load File nodes into Neo4j."""
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer7_commits.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Load files one at a time
            files = data['nodes']['files']
            for file_data in files:
                # Create File object (no relationships embedded)
                file = File(
                    id=file_data['id'],
                    path=file_data['path'],
                    name=file_data['name'],
                    extension=file_data['extension'],
                    language=file_data['language'],
                    is_test=file_data['is_test'],
                    size=file_data['size'],
                    created_at=file_data['created_at']
                )
                
                # Merge file (without relationships for now)
                merge_file(session, file)
            
            print(f"✓ Loaded {len(files)} files")
    
    finally:
        driver.close()


def load_relationships():
    """Load all Layer 7 relationships.
    
    Relationships:
    - PART_OF: Commit → Branch (no properties)
    - AUTHORED_BY: Commit ↔ Person (undirected, no properties)
    - MODIFIES: Commit → File (with additions/deletions properties)
    - REFERENCES: Commit → Issue (no properties)
    """
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer7_commits.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Group relationships by type for reporting
            rel_counts = {}
            
            # Process relationships one at a time
            for rel_data in data['relationships']:
                rel_type = rel_data['type']
                rel_counts[rel_type] = rel_counts.get(rel_type, 0) + 1
                
                # Create Relationship object (with properties if present)
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
            
            # Report relationship counts
            print(f"✓ Loaded {len(data['relationships'])} relationships:")
            for rel_type, count in sorted(rel_counts.items()):
                print(f"  - {rel_type}: {count}")
    
    finally:
        driver.close()


def validate_layer7():
    """Run validation queries to verify Layer 7 data."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            print("\n" + "=" * 60)
            print("LAYER 7 VALIDATION")
            print("=" * 60)
            
            # 1. Node counts
            result = session.run("MATCH (c:Commit) RETURN count(c) as count")
            commit_count = result.single()['count']
            
            result = session.run("MATCH (f:File) RETURN count(f) as count")
            file_count = result.single()['count']
            
            print(f"\n1. Total Nodes:")
            print(f"   Commits: {commit_count}")
            print(f"   Files: {file_count}")
            
            # 2. Commits by author (top 10)
            print("\n2. Top 10 Commit Authors:")
            result = session.run("""
                MATCH (c:Commit)-[:AUTHORED_BY]-(p:Person)
                RETURN p.name, count(c) as commits
                ORDER BY commits DESC
                LIMIT 10
            """)
            for record in result:
                print(f"   {record['p.name']}: {record['commits']} commits")
            
            # 3. Most modified files
            print("\n3. Top 10 Most Modified Files:")
            result = session.run("""
                MATCH (c:Commit)-[m:MODIFIES]->(f:File)
                RETURN f.path, 
                       count(c) as modifications,
                       sum(m.additions) as total_additions,
                       sum(m.deletions) as total_deletions
                ORDER BY modifications DESC
                LIMIT 10
            """)
            for record in result:
                print(f"   {record['f.path']}: {record['modifications']} changes "
                      f"(+{record['total_additions']}/-{record['total_deletions']})")
            
            # 4. Commits with Jira references
            print("\n4. Jira Reference Statistics:")
            result = session.run("""
                MATCH (c:Commit)
                OPTIONAL MATCH (c)-[:REFERENCES]->(i:Issue)
                RETURN count(DISTINCT c) as total_commits,
                       count(DISTINCT i) as referenced_issues,
                       count(DISTINCT CASE WHEN i IS NOT NULL THEN c END) as commits_with_refs
            """)
            record = result.single()
            total = record['total_commits']
            with_refs = record['commits_with_refs']
            percent = (with_refs / total * 100) if total > 0 else 0
            print(f"   Total commits: {total}")
            print(f"   Commits with Jira refs: {with_refs} ({percent:.1f}%)")
            print(f"   Unique issues referenced: {record['referenced_issues']}")
            
            # 5. Commits per branch
            print("\n5. Commits per Branch:")
            result = session.run("""
                MATCH (c:Commit)-[:PART_OF]->(b:Branch)
                RETURN b.name, count(c) as commits
                ORDER BY commits DESC
            """)
            for record in result:
                print(f"   {record['b.name']}: {record['commits']} commits")
            
            # 6. File types distribution
            print("\n6. Files by Language:")
            result = session.run("""
                MATCH (f:File)
                RETURN f.language, count(f) as file_count
                ORDER BY file_count DESC
            """)
            for record in result:
                print(f"   {record['f.language']}: {record['file_count']} files")
            
            # 7. Verify bidirectional relationships
            print("\n7. Bidirectional Relationship Verification:")
            
            # Check PART_OF → CONTAINS
            result = session.run("""
                MATCH (c:Commit)-[:PART_OF]->(b:Branch)
                WHERE NOT exists((b)-[:CONTAINS]->(c))
                RETURN count(*) as missing
            """)
            count = result.single()['missing']
            if count == 0:
                print("   ✓ PART_OF ↔ CONTAINS: All bidirectional")
            else:
                print(f"   ✗ PART_OF ↔ CONTAINS: {count} missing reverse")
            
            # Check MODIFIES → MODIFIED_BY (with property matching)
            result = session.run("""
                MATCH (c:Commit)-[m1:MODIFIES]->(f:File)
                MATCH (f)-[m2:MODIFIED_BY]->(c)
                WHERE m1.additions <> m2.additions OR m1.deletions <> m2.deletions
                RETURN count(*) as mismatched
            """)
            count = result.single()['mismatched']
            if count == 0:
                print("   ✓ MODIFIES ↔ MODIFIED_BY: All properties match")
            else:
                print(f"   ✗ MODIFIES ↔ MODIFIED_BY: {count} property mismatches")
            
            print("\n" + "=" * 60)
    
    finally:
        driver.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Loading Layer 7: Git Commits & Files")
    print("=" * 60)
    
    load_commits_to_neo4j()
    load_files_to_neo4j()
    load_relationships()
    validate_layer7()
    
    print("\n✓ Layer 7 loading complete!")
