import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load environment variables from the project root .env
project_root = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(project_root / ".env")

# Neo4j configuration from environment
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

def read_cypher_query(filename: str) -> str:
    """Reads a cypher query from the adjacent 'queries' directory."""
    query_path = Path(__file__).parent / "queries" / filename
    if not query_path.exists():
        raise FileNotFoundError(f"Could not find query file at {query_path}")
    
    with open(query_path, "r") as f:
        return f.read()

def run_test():
    print("=== Collaboration Network Test Runner ===\n")
    
    query = read_cypher_query("collaboration_score.cypher")
    print(f"Loaded query from file. Length: {len(query)} characters.")
    
    print(f"Connecting to Neo4j at {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            print("Executing query... (this might take a moment depending on graph size)")
            
            start_time = time.time()
            result = session.run(query)
            records = list(result)
            execution_time = time.time() - start_time
            
            print(f"\nQuery completed in {execution_time:.2f} seconds.")
            print(f"Found {len(records)} collaboration pairs.")
            
            if records:
                print("\nTop 15 Collaborators:")
                print("-" * 65)
                print(f"{'Person 1':<25} | {'Person 2':<25} | {'Score':<6}")
                print("-" * 65)
                
                for record in records[:15]:
                    # Gracefully handle missing names if schema differs slightly
                    p1_name = record.get("person1", "Unknown") or "Unknown"
                    p2_name = record.get("person2", "Unknown") or "Unknown"
                    score = record.get("total_collaboration_score", 0)
                    print(f"{p1_name:<25} | {p2_name:<25} | {score:<6}")
    finally:
        driver.close()

if __name__ == "__main__":
    run_test()