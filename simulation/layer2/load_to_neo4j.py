"""
Layer 2 Neo4j Loader: Load Jira Initiatives into Neo4j
Loads Project and Initiative nodes and creates relationships to existing Person nodes.
DOES NOT clear existing data - this is an incremental load.
"""
import sys
import json
import os
import traceback

from neo4j import GraphDatabase
from db.models import (
    Project, Initiative, Relationship,
    merge_project, merge_initiative, merge_relationship,
    create_constraints, DIRECTIONAL_RELATIONSHIPS
)

class Layer2Loader:
    def __init__(self, uri: str, user: str, password: str):
        """Initialize Neo4j connection."""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        """Close the driver connection."""
        self.driver.close()
    
    def create_constraints(self):
        """Create uniqueness constraints for node IDs."""
        with self.driver.session() as session:
            print("\nCreating constraints...")
            create_constraints(session, layers=[2])
            print("   ✓ Constraints created/verified")
    
    def verify_layer1_data(self):
        """Verify that Layer 1 data exists in the database."""
        with self.driver.session() as session:
            print("\nVerifying Layer 1 data...")
            
            # Check for people
            result = session.run("MATCH (p:Person) RETURN count(p) as count")
            person_count = result.single()['count']
            
            if person_count == 0:
                raise Exception("No Person nodes found! Please load Layer 1 first.")
            
            print(f"   ✓ Found {person_count} Person nodes")
            
            # Check for teams
            result = session.run("MATCH (t:Team) RETURN count(t) as count")
            team_count = result.single()['count']
            print(f"   ✓ Found {team_count} Team nodes")
    
    def load_project(self, project_data: dict):
        """Load Project node into Neo4j."""
        with self.driver.session() as session:
            print(f"\nLoading project: {project_data['name']}...")
            
            project = Project(**project_data)
            merge_project(session, project)
            
            print("   ✓ Merged Project node")
    
    def load_initiatives(self, initiatives: list):
        """Load Initiative nodes into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(initiatives)} initiatives...")
            
            for initiative_data in initiatives:
                # Extract assignee_id and reporter_id for relationships
                assignee_person_id = initiative_data.pop('assignee_id', None)
                reporter_person_id = initiative_data.pop('reporter_id', None)
                
                initiative = Initiative(**initiative_data)
                
                # Create relationships directly to Person nodes
                relationships = []
                
                if assignee_person_id:
                    relationships.append(Relationship(
                        type="ASSIGNED_TO",
                        from_id=initiative.id,
                        to_id=assignee_person_id,
                        from_type="Initiative",
                        to_type="Person"
                    ))
                
                if reporter_person_id:
                    relationships.append(Relationship(
                        type="REPORTED_BY",
                        from_id=initiative.id,
                        to_id=reporter_person_id,
                        from_type="Initiative",
                        to_type="Person"
                    ))
                
                # Merge initiative with relationships
                merge_initiative(session, initiative, relationships=relationships)
                print(f"   ✓ Merged {initiative.key}: {initiative.summary}")
    
    def load_relationships(self, relationships: list):
        """Load all relationships into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(relationships)} relationships...")
            
            # Group by relationship type for better reporting
            rel_counts = {}
            skipped_count = 0
            
            for rel_data in relationships:
                rel_type = rel_data['type']
                
                # Skip ASSIGNED_TO and REPORTED_BY as they're handled in load_initiatives
                if rel_type in ["ASSIGNED_TO", "REPORTED_BY"]:
                    skipped_count += 1
                    continue
                
                if rel_type not in rel_counts:
                    rel_counts[rel_type] = 0
                
                # Create Relationship object and merge
                relationship = Relationship(**rel_data)
                merge_relationship(session, relationship)
                
                # Count directional pairs as 2 (reverse edge is created automatically)
                increment = 2 if rel_type in DIRECTIONAL_RELATIONSHIPS else 1
                rel_counts[rel_type] = rel_counts.get(rel_type, 0) + increment
            
            # Report results
            for rel_type, count in rel_counts.items():
                print(f"   ✓ {rel_type}: {count} (includes reverse edges for directional pairs)")
            
            if skipped_count > 0:
                print(f"   - Skipped {skipped_count} ASSIGNED_TO/REPORTED_BY relationships (handled separately)")
    
    def run_validation_queries(self):
        """Run validation queries from the simulation plan."""
        print("\n" + "=" * 60)
        print("VALIDATION QUERIES")
        print("=" * 60)
        
        with self.driver.session() as session:
            # Query 1: List all initiatives with assignees and reporters
            print("\n1. Initiatives with assignees and reporters:")
            query1 = """
            MATCH (i:Initiative)-[:ASSIGNED_TO]-(assignee:Person)
            MATCH (i)-[:REPORTED_BY]-(reporter:Person)
            RETURN i.key, i.summary, assignee.name as assignee, reporter.name as reporter, i.status
            ORDER BY i.key
            """
            result = session.run(query1)
            for record in result:
                print(f"   {record['i.key']}: {record['i.summary']}")
                print(f"      Assignee: {record['assignee']}, Reporter: {record['reporter']}, Status: {record['i.status']}")
            
            # Query 2: Timeline view
            print("\n2. Initiative timeline:")
            query2 = """
            MATCH (i:Initiative)
            RETURN i.key, i.summary, i.start_date, i.due_date
            ORDER BY i.start_date, i.due_date
            """
            result = session.run(query2)
            for record in result:
                print(f"   {record['i.key']}: {record['i.start_date']} → {record['i.due_date']}")
                print(f"      {record['i.summary']}")
            
            # Query 3: Verify PART_OF relationships
            print("\n3. Initiatives by project:")
            query3 = """
            MATCH (p:Project)<-[:PART_OF]-(i:Initiative)
            RETURN p.name, collect(i.key) as initiatives
            """
            result = session.run(query3)
            for record in result:
                print(f"   {record['p.name']}: {', '.join(record['initiatives'])}")
            
            # Node counts
            print("\n4. Total node counts:")
            query4 = """
            MATCH (n)
            RETURN labels(n)[0] as label, count(*) as count
            ORDER BY label
            """
            result = session.run(query4)
            for record in result:
                print(f"   {record['label']:20} {record['count']:3}")

def main():
    """Main loader function."""
    print("=" * 60)
    print("Layer 2 Neo4j Loader - Incremental Load")
    print("=" * 60)
    
    # Read environment variables
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
    
    # Read data file
    data_path = "../data/layer2_initiatives.json"
    print(f"\nReading data from {data_path}...")
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("   ✓ Data loaded successfully")
    except FileNotFoundError:
        print(f"   ✗ Error: {data_path} not found!")
        print("   Please run generate_data.py first.")
        sys.exit(1)
    
    # Initialize loader
    print(f"\nConnecting to Neo4j at {neo4j_uri}...")
    loader = Layer2Loader(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        # Verify Layer 1 data exists
        loader.verify_layer1_data()
        
        # Create constraints
        loader.create_constraints()
        
        # Load nodes
        loader.load_project(data['nodes']['project'])
        loader.load_initiatives(data['nodes']['initiatives'])
        
        # Load relationships
        loader.load_relationships(data['relationships'])
        
        # Run validation
        loader.run_validation_queries()
        
        print("\n" + "=" * 60)
        print("✓ Layer 2 loaded successfully!")
        print("=" * 60)
        print("\nYou can now:")
        print("1. Open Neo4j Browser at http://localhost:7474")
        print("2. Run queries to explore initiatives")
        print("3. Proceed to Layer 3 (Jira Epics)")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        loader.close()

if __name__ == "__main__":
    main()
