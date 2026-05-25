"""
Quick validation test for the refactored models
Tests data classes and basic validation without connecting to Neo4j
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock neo4j Session to avoid import error
from unittest.mock import MagicMock
sys.modules['neo4j'] = MagicMock()

from models import Person, Team, IdentityMapping, Relationship

def test_person_creation():
    """Test Person dataclass creation."""
    person = Person(
        id="person_test",
        name="Test User",
        email="test@example.com",
        title="Software Engineer",
        role="Engineer",
        seniority="Mid",
        hire_date="2024-01-15",
        is_manager=False
    )
    
    props = person.to_neo4j_properties()
    assert props['id'] == "person_test"
    assert props['name'] == "Test User"
    assert props['is_manager'] == False
    print("✓ Person creation works")

def test_team_creation():
    """Test Team dataclass creation."""
    team = Team(
        id="team_test",
        name="Test Team",

        target_size=10,
        created_at="2024-01-01"
    )
    
    props = team.to_neo4j_properties()
    assert props['id'] == "team_test"
    assert props['target_size'] == 10
    print("✓ Team creation works")

def test_identity_creation():
    """Test IdentityMapping dataclass creation."""
    identity = IdentityMapping(
        id="identity_test",
        provider="GitHub",
        username="testuser",
        email="test@example.com"
    )
    
    props = identity.to_neo4j_properties()
    assert props['provider'] == "GitHub"
    print("✓ IdentityMapping creation works")

def test_relationship_creation():
    """Test Relationship dataclass creation."""
    rel = Relationship(
        type="MEMBER_OF",
        from_id="person_test",
        to_id="team_test",
        from_type="Person",
        to_type="Team",
        properties={"since": "2024-01-01"}
    )
    
    assert rel.type == "MEMBER_OF"
    assert rel.properties['since'] == "2024-01-01"
    print("✓ Relationship creation works")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Refactored Models")
    print("=" * 60)
    print()
    
    try:
        test_person_creation()
        test_team_creation()
        test_identity_creation()
        test_relationship_creation()
        
        print()
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
