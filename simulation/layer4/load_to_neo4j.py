"""
Layer 4 Neo4j Loader: Load Jira Stories, Bugs, Tasks & Sprints into Neo4j
Loads Issue and Sprint nodes and creates relationships to existing Epic, Person, and Sprint nodes.
DOES NOT clear existing data - this is an incremental load.
"""
import sys
import json
import os
import traceback

from neo4j import GraphDatabase
from connectors.db.models import (
    Issue, Sprint, Relationship,
    merge_issue, merge_sprint, merge_relationship,
    create_constraints, DIRECTIONAL_RELATIONSHIPS
)

class Layer4Loader:
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
            create_constraints(session, layers=[4])
            print("   ✓ Constraints created/verified")
    
    def verify_previous_layers(self):
        """Verify that Layers 1-3 data exists in the database."""
        with self.driver.session() as session:
            print("\nVerifying previous layers...")
            
            # Check Layer 1
            result = session.run("MATCH (p:Person) RETURN count(p) as count")
            person_count = result.single()['count']
            if person_count == 0:
                raise Exception("No Person nodes found! Please load Layer 1 first.")
            print(f"   ✓ Layer 1: {person_count} Person nodes")
            
            # Check Layer 2
            result = session.run("MATCH (i:Initiative) RETURN count(i) as count")
            initiative_count = result.single()['count']
            if initiative_count == 0:
                raise Exception("No Initiative nodes found! Please load Layer 2 first.")
            print(f"   ✓ Layer 2: {initiative_count} Initiative nodes")
            
            # Check Layer 3
            result = session.run("MATCH (e:Epic) RETURN count(e) as count")
            epic_count = result.single()['count']
            if epic_count == 0:
                raise Exception("No Epic nodes found! Please load Layer 3 first.")
            print(f"   ✓ Layer 3: {epic_count} Epic nodes")
    
    def load_sprints(self, sprints: list):
        """Load Sprint nodes into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(sprints)} sprints...")
            
            for sprint_data in sprints:
                sprint = Sprint(**sprint_data)
                merge_sprint(session, sprint)
                print(f"   ✓ Merged {sprint.name}")
    
    def load_issues(self, issues: list):
        """Load Issue nodes into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(issues)} issues...")
            
            issue_counts = {"Story": 0, "Bug": 0, "Task": 0}
            
            for issue_data in issues:
                # Extract relationship IDs
                epic_id = issue_data.pop('epic_id', None)
                assignee_person_id = issue_data.pop('assignee_id', None)
                reporter_person_id = issue_data.pop('reporter_id', None)
                related_story_id = issue_data.pop('related_story_id', None)  # For bugs
                
                issue = Issue(**issue_data)
                
                # Create relationships directly to Epic, Person nodes
                relationships = []
                
                if epic_id:
                    relationships.append(Relationship(
                        type="PART_OF",
                        from_id=issue.id,
                        to_id=epic_id,
                        from_type="Issue",
                        to_type="Epic"
                    ))
                
                if assignee_person_id:
                    relationships.append(Relationship(
                        type="ASSIGNED_TO",
                        from_id=issue.id,
                        to_id=assignee_person_id,
                        from_type="Issue",
                        to_type="Person"
                    ))
                
                if reporter_person_id:
                    relationships.append(Relationship(
                        type="REPORTED_BY",
                        from_id=issue.id,
                        to_id=reporter_person_id,
                        from_type="Issue",
                        to_type="Person"
                    ))
                
                # Note: related_story_id handled via RELATES_TO in relationships array
                
                # Merge issue with relationships
                merge_issue(session, issue, relationships=relationships)
                issue_counts[issue.type] += 1
            
            print(f"   ✓ Stories: {issue_counts['Story']}")
            print(f"   ✓ Bugs: {issue_counts['Bug']}")
            print(f"   ✓ Tasks: {issue_counts['Task']}")
    
    def load_relationships(self, relationships: list):
        """Load all relationships into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(relationships)} relationships...")
            
            # Group by relationship type for better reporting
            rel_counts = {}
            skipped_count = 0
            
            for rel_data in relationships:
                rel_type = rel_data['type']
                
                # Skip relationships already handled in load_issues
                if rel_type in ["PART_OF", "ASSIGNED_TO", "REPORTED_BY"]:
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
                print(f"   - Skipped {skipped_count} relationships (handled in load_issues)")
    
    def run_validation_queries(self):
        """Run validation queries from the simulation plan."""
        print("\n" + "=" * 60)
        print("VALIDATION QUERIES")
        print("=" * 60)
        
        with self.driver.session() as session:
            # Query 1: Sprint burndown data
            print("\n1. Sprint burndown data:")
            query1 = """
            MATCH (s:Sprint)<-[:IN_SPRINT]-(i:Issue)
            RETURN s.name, 
                   sum(i.story_points) as total_points,
                   sum(CASE WHEN i.status = 'Done' THEN i.story_points ELSE 0 END) as completed_points,
                   count(i) as issue_count
            ORDER BY s.name
            """
            result = session.run(query1)
            for record in result:
                completion = (record['completed_points'] / record['total_points'] * 100) if record['total_points'] > 0 else 0
                print(f"   {record['s.name']}: {record['completed_points']}/{record['total_points']} points ({completion:.1f}%), {record['issue_count']} issues")
            
            # Query 2: Find blocked work
            print("\n2. Blocked work:")
            query2 = """
            MATCH (blocked:Issue {status: 'Blocked'})-[:BLOCKS]-(blocker:Issue)
            RETURN blocked.key, blocked.summary, collect(blocker.key) as blocking_issues
            """
            result = session.run(query2)
            records = list(result)
            if not records:
                print("   ✓ No blocked issues")
            else:
                for record in records:
                    print(f"   {record['blocked.key']}: {record['blocked.summary']}")
                    print(f"      Blocked by: {', '.join(record['blocking_issues'])}")
            
            # Query 3: Bug distribution by type
            print("\n3. Issue type distribution:")
            query3 = """
            MATCH (i:Issue)
            RETURN i.type, count(*) as count
            ORDER BY count DESC
            """
            result = session.run(query3)
            for record in result:
                print(f"   {record['i.type']}: {record['count']}")
            
            # Query 4: Status distribution
            print("\n4. Issue status distribution:")
            query4 = """
            MATCH (i:Issue)
            RETURN i.status, count(*) as count
            ORDER BY count DESC
            """
            result = session.run(query4)
            for record in result:
                print(f"   {record['i.status']}: {record['count']}")
            
            # Query 5: Bugs linked to stories
            print("\n5. Bugs related to stories:")
            query5 = """
            MATCH (bug:Issue {type: 'Bug'})-[:RELATES_TO]-(story:Issue {type: 'Story'})
            RETURN bug.key, story.key as story, bug.summary
            """
            result = session.run(query5)
            records = list(result)
            print(f"   Found {len(records)} bugs linked to stories")
            for record in records[:3]:  # Show first 3
                print(f"   {record['bug.key']} → {record['story']}: {record['bug.summary']}")
            
            # Node counts
            print("\n6. Total node counts:")
            query6 = """
            MATCH (n)
            RETURN labels(n)[0] as label, count(*) as count
            ORDER BY label
            """
            result = session.run(query6)
            for record in result:
                print(f"   {record['label']:20} {record['count']:3}")

def main():
    """Main loader function."""
    print("=" * 60)
    print("Layer 4 Neo4j Loader - Incremental Load")
    print("=" * 60)
    
    # Read environment variables
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
    
    # Read data file
    data_path = "../data/layer4_stories_bugs.json"
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
    loader = Layer4Loader(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        # Verify previous layers
        loader.verify_previous_layers()
        
        # Create constraints
        loader.create_constraints()
        
        # Load nodes
        loader.load_sprints(data['nodes']['sprints'])
        loader.load_issues(data['nodes']['issues'])
        
        # Load relationships
        loader.load_relationships(data['relationships'])
        
        # Run validation
        loader.run_validation_queries()
        
        print("\n" + "=" * 60)
        print("✓ Layer 4 loaded successfully!")
        print("=" * 60)
        print("\nYou can now:")
        print("1. Open Neo4j Browser at http://localhost:7474")
        print("2. Run sprint burndown and velocity queries")
        print("3. Analyze work item distribution and dependencies")
        print("4. Proceed to Layer 5 (Git Repositories)")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        loader.close()

if __name__ == "__main__":
    main()
