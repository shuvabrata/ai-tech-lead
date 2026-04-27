"""
Reset Neo4j Database: Clear all nodes and relationships
Use this script with caution - it will delete all data in the database.
"""
import os
import sys
from neo4j import GraphDatabase


def clear_database(uri: str, user: str, password: str):
    """Clear all nodes and relationships from Neo4j database."""
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            print("⚠️  Clearing database...")
            session.run("""
            CALL apoc.periodic.iterate(
            'MATCH (n) RETURN n',
            'DETACH DELETE n',
            {batchSize: 10000}
            )
            """)            
            print("   ✓ Database cleared")
    finally:
        driver.close()


def main():
    """Main reset function."""
    print("=" * 60)
    print("Neo4j Database Reset")
    print("=" * 60)
    
    # Read environment variables
    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
    
    print(f"\nConnecting to Neo4j at {neo4j_uri}...")
    
    # Ask for confirmation
    print("\n⚠️  WARNING: This will DELETE ALL existing data in Neo4j!")
    print("This action cannot be undone.")
    response = input("\nAre you absolutely sure? (type 'DELETE' to confirm): ")
    
    if response != 'DELETE':
        print("Aborted.")
        return
    
    try:
        clear_database(neo4j_uri, neo4j_user, neo4j_password)
        
        print("\n" + "=" * 60)
        print("✓ Database cleared successfully!")
        print("=" * 60)
        print("\nYou can now reload data using the layer loaders.")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
