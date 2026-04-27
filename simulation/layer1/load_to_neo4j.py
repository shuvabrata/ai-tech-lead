"""
Layer 1 Neo4j Loader: Merge People & Teams data into Neo4j
Reads the generated JSON and merges nodes and relationships in Neo4j.
Uses MERGE operations - existing data is preserved.
To clear the database first, run reset_db.py
"""
import sys
import json
import os
import traceback

from neo4j import GraphDatabase
from db.models import (
    Person, Team, IdentityMapping, Relationship,
    merge_person, merge_team, merge_identity_mapping, merge_relationship,
    create_constraints, DIRECTIONAL_RELATIONSHIPS
)

class Layer1Loader:
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
            create_constraints(session, layers=[1])
            print("   ✓ Constraints created/verified")
    
    def load_people(self, people: list):
        """Load Person nodes into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(people)} people...")
            
            for person_data in people:
                person = Person(**person_data)
                merge_person(session, person)
            
            print(f"   ✓ Merged {len(people)} Person nodes")
    
    def load_teams(self, teams: list):
        """Load Team nodes into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(teams)} teams...")
            
            for team_data in teams:
                team = Team(**team_data)
                merge_team(session, team)
            
            print(f"   ✓ Merged {len(teams)} Team nodes")
    
    def load_identity_mappings(self, mappings: list):
        """Load IdentityMapping nodes into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(mappings)} identity mappings...")
            
            for mapping_data in mappings:
                # Extract person_id for relationship, not part of IdentityMapping node
                person_id = mapping_data.pop('person_id', None)
                
                identity = IdentityMapping(**mapping_data)
                
                # Create relationship to Person if person_id exists
                relationships = []
                if person_id:
                    relationships.append(Relationship(
                        type="MAPS_TO",
                        from_id=identity.id,
                        to_id=person_id,
                        from_type="IdentityMapping",
                        to_type="Person"
                    ))
                
                merge_identity_mapping(session, identity, relationships=relationships)
            
            print(f"   ✓ Merged {len(mappings)} IdentityMapping nodes")
    
    def load_relationships(self, relationships: list):
        """Load all relationships into Neo4j one at a time."""
        with self.driver.session() as session:
            print(f"\nLoading {len(relationships)} relationships...")
            
            # Group by relationship type for better reporting
            rel_counts = {}
            skipped_count = 0
            
            for rel_data in relationships:
                rel_type = rel_data['type']
                
                # Skip MAPS_TO relationships as they're handled in load_identity_mappings
                if rel_type == "MAPS_TO":
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
                print(f"   - Skipped {skipped_count} MAPS_TO relationships (handled separately)")
    
    def run_validation_queries(self):
        """Run validation queries from the simulation plan."""
        print("\n" + "=" * 60)
        print("VALIDATION QUERIES")
        print("=" * 60)
        
        with self.driver.session() as session:
            # Query 1: Count people by role and seniority
            print("\n1. People by role and seniority:")
            query1 = """
            MATCH (p:Person)
            RETURN p.role as role, p.seniority as seniority, count(*) as count
            ORDER BY role, seniority
            """
            result = session.run(query1)
            for record in result:
                role = record['role'] if record['role'] is not None else "N/A"
                seniority = record['seniority'] if record['seniority'] is not None else "N/A"
                print(f"   {role:20} {seniority:10} {record['count']:3}")
            
            # Query 2: Org hierarchy (sample)
            print("\n2. Org hierarchy (sample - first 10):")
            query2 = """
            MATCH (p:Person)-[:REPORTS_TO]->(m:Person)
            RETURN p.name, m.name as manager, p.title
            LIMIT 10
            """
            result = session.run(query2)
            for record in result:
                print(f"   {record['p.name']:20} → {record['manager']:20} ({record['p.title']})")
            
            # Query 3: Team sizes
            print("\n3. Team sizes:")
            query3 = """
            MATCH (t:Team)-[:MEMBER_OF]-(p:Person)
            RETURN t.name, count(p) as team_size
            ORDER BY team_size DESC
            """
            result = session.run(query3)
            for record in result:
                print(f"   {record['t.name']:20} {record['team_size']:3} members")
            
            # Additional validation: Managers
            print("\n4. Managers and their teams:")
            query4 = """
            MATCH (m:Person)-[:MANAGES]->(t:Team)
            RETURN m.name, t.name as team
            """
            result = session.run(query4)
            for record in result:
                print(f"   {record['m.name']:20} → {record['team']}")
            
            # Additional validation: Identity mappings
            print("\n5. Identity mapping providers:")
            query5 = """
            MATCH (i:IdentityMapping)
            RETURN i.provider, count(*) as count
            """
            result = session.run(query5)
            for record in result:
                print(f"   {record['i.provider']:10} {record['count']:3} mappings")

def main():
    """Main loader function."""
    print("=" * 60)
    print("Layer 1 Neo4j Loader")
    print("=" * 60)
    
    # Read environment variables
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
    
    # Read data file
    data_path = "../data/layer1_people_teams.json"
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
    loader = Layer1Loader(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        # Create constraints
        loader.create_constraints()
        
        # Load nodes
        loader.load_people(data['nodes']['people'])
        loader.load_teams(data['nodes']['teams'])
        loader.load_identity_mappings(data['nodes']['identity_mappings'])
        
        # Load relationships
        loader.load_relationships(data['relationships'])
        
        # Run validation
        loader.run_validation_queries()
        
        print("\n" + "=" * 60)
        print("✓ Layer 1 data merged successfully!")
        print("=" * 60)
        print("\nNote: Data was MERGED (not replaced).")
        print("To clear the database first, run: python reset_db.py")
        print("\nYou can now:")
        print("1. Open Neo4j Browser at http://localhost:7474")
        print("2. Run queries to explore the data")
        print("3. Proceed to Layer 2 (Jira Initiatives)")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        loader.close()

if __name__ == "__main__":
    main()
