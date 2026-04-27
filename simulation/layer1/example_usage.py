"""
Example usage of the refactored models and utilities.
Demonstrates how to merge nodes one at a time in real-world scenarios.
"""

import os

from neo4j import GraphDatabase
from db.models import (
    Person, Team, IdentityMapping, Relationship,
    merge_person, merge_team, merge_identity_mapping, merge_relationship,
    create_constraints
)


def example_1_merge_person_only():
    """Example: Merge a single person without relationships."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Create constraints first
            create_constraints(session)
            
            # Create a person
            person = Person(
                id="person_john_doe",
                name="John Doe",
                email="john.doe@company.com",
                title="Senior Software Engineer",
                role="Engineer",
                seniority="Senior",
                hire_date="2024-05-15",
                is_manager=False
            )
            
            # Merge the person (no relationships yet)
            merge_person(session, person)
            print("✓ Person merged successfully")
    
    finally:
        driver.close()


def example_2_merge_person_with_team():
    """Example: Merge a person and immediately create team relationship."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            create_constraints(session)
            
            # First, ensure the team exists
            team = Team(
                id="team_engineering",
                name="Engineering Team",
                target_size=10,
                created_at="2024-01-01"
            )
            merge_team(session, team)
            
            # Create a person with a team relationship
            person = Person(
                id="person_jane_smith",
                name="Jane Smith",
                email="jane.smith@company.com",
                title="Software Engineer",
                role="Engineer",
                seniority="Mid",
                hire_date="2024-08-01",
                is_manager=False
            )
            
            # Define the MEMBER_OF relationship
            member_rel = Relationship(
                type="MEMBER_OF",
                from_id=person.id,
                to_id=team.id,
                from_type="Person",
                to_type="Team"
            )
            
            # Merge person with relationship
            merge_person(session, person, relationships=[member_rel])
            print("✓ Person merged with team relationship")
    
    finally:
        driver.close()


def example_3_add_relationship_later():
    """Example: Merge a person first, then add relationships later."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            create_constraints(session)
            
            # Step 1: Merge person without any relationships
            person = Person(
                id="person_alice_johnson",
                name="Alice Johnson",
                email="alice.johnson@company.com",
                title="Engineering Manager",
                role="Manager",
                seniority="Manager",
                hire_date="2023-03-15",
                is_manager=True
            )
            merge_person(session, person)
            print("✓ Person merged")
            
            # Step 2: Later, add team management relationship
            team = Team(
                id="team_platform",
                name="Platform Team",
                target_size=12,
                created_at="2023-01-01"
            )
            merge_team(session, team)
            
            manages_rel = Relationship(
                type="MANAGES",
                from_id=person.id,
                to_id=team.id,
                from_type="Person",
                to_type="Team"
            )
            merge_relationship(session, manages_rel)
            print("✓ Management relationship added")
            
            # Step 3: Even later, add identity mapping with relationship
            github_identity = IdentityMapping(
                id="identity_github_alice",
                provider="GitHub",
                username="alicej",
                email="alice.johnson@company.com"
            )
            
            # Create the MAPS_TO relationship to link identity to person
            maps_to_rel = Relationship(
                type="MAPS_TO",
                from_id=github_identity.id,
                to_id=person.id,
                from_type="IdentityMapping",
                to_type="Person"
            )
            
            # Merge identity with relationship in one call
            merge_identity_mapping(session, github_identity, relationships=[maps_to_rel])
            print("✓ Identity mapping added")
    
    finally:
        driver.close()


def example_4_relationship_creates_missing_nodes():
    """Example: Create relationship even if target node doesn't exist yet."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            create_constraints(session)
            
            # Create a REPORTS_TO relationship
            # The merge_relationship function will create placeholder nodes if they don't exist
            reports_to_rel = Relationship(
                type="REPORTS_TO",
                from_id="person_bob_wilson",
                to_id="person_carol_manager",
                from_type="Person",
                to_type="Person"
            )
            
            merge_relationship(session, reports_to_rel)
            print("✓ Relationship created (nodes auto-created with just IDs)")
            
            # Later, you can update the person with full details
            bob = Person(
                id="person_bob_wilson",
                name="Bob Wilson",
                email="bob.wilson@company.com",
                title="Software Engineer",
                role="Engineer",
                seniority="Mid",
                hire_date="2024-06-01",
                is_manager=False
            )
            merge_person(session, bob)
            print("✓ Person details updated")
    
    finally:
        driver.close()


def example_5_streaming_data():
    """Example: Process streaming data (e.g., from API, Kafka, etc.).
    
    Note: In real scenarios, you'd create IdentityMapping separately from Person
    and link them via MAPS_TO relationships based on email or other identifiers.
    """
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            create_constraints(session)
            
            # Simulate receiving data one at a time from an API or stream
            incoming_people = [
                {
                    "id": "person_stream_1",
                    "name": "Stream User 1",
                    "email": "stream1@company.com",
                    "title": "Engineer",
                    "role": "Engineer",
                    "seniority": "Mid",
                    "hire_date": "2024-09-01",
                    "is_manager": False,
                    "team_id": "team_data"
                },
                {
                    "id": "person_stream_2",
                    "name": "Stream User 2",
                    "email": "stream2@company.com",
                    "title": "Senior Engineer",
                    "role": "Engineer",
                    "seniority": "Senior",
                    "hire_date": "2023-04-15",
                    "is_manager": False,
                    "team_id": "team_data"
                }
            ]
            
            # Process each person as they arrive
            for person_data in incoming_people:
                team_id = person_data.pop('team_id')  # Remove team_id from person data
                
                person = Person(**person_data)
                
                # If we have team information, create the relationship
                if team_id:
                    member_rel = Relationship(
                        type="MEMBER_OF",
                        from_id=person.id,
                        to_id=team_id,
                        from_type="Person",
                        to_type="Team"
                    )
                    merge_person(session, person, relationships=[member_rel])
                else:
                    merge_person(session, person)
                
                print(f"✓ Processed {person.name}")
    
    finally:
        driver.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Example Usage Demonstrations")
    print("=" * 60)
    
    print("\nExample 1: Merge person only")
    print("-" * 60)
    # Uncomment to run:
    # example_1_merge_person_only()
    
    print("\nExample 2: Merge person with team relationship")
    print("-" * 60)
    # Uncomment to run:
    # example_2_merge_person_with_team()
    
    print("\nExample 3: Add relationships later")
    print("-" * 60)
    # Uncomment to run:
    # example_3_add_relationship_later()
    
    print("\nExample 4: Relationship creates missing nodes")
    print("-" * 60)
    # Uncomment to run:
    # example_4_relationship_creates_missing_nodes()
    
    print("\nExample 5: Streaming data")
    print("-" * 60)
    # Uncomment to run:
    # example_5_streaming_data()
    
    print("\n" + "=" * 60)
    print("Uncomment the examples you want to run!")
    print("=" * 60)
