"""
Layer 1 Data Generation: People & Teams Foundation
Generates realistic organizational structure with 57 people across 5 teams.
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

# Team configuration
TEAMS = [
    {"name": "Platform Team", "size": 12, "focus": "Infrastructure, DevOps, Security"},
    {"name": "API Team", "size": 10, "focus": "Backend Services, Microservices"},
    {"name": "Frontend Team", "size": 10, "focus": "Web UI, React, TypeScript"},
    {"name": "Mobile Team", "size": 8, "focus": "iOS, Android, React Native"},
    {"name": "Data Team", "size": 10, "focus": "Data Engineering, Analytics, ML"}
]

# Engineering roles and seniority distribution
ENGINEER_DISTRIBUTION = {
    "Junior Software Engineer": 10,
    "Software Engineer": 25,
    "Senior Software Engineer": 10,
    "Staff Software Engineer": 5
}

# First and last names for realistic people
FIRST_NAMES = [
    "Alex", "Jordan", "Casey", "Morgan", "Taylor", "Riley", "Avery", "Quinn",
    "Jamie", "Skylar", "Cameron", "Drew", "Finley", "Sage", "River", "Phoenix",
    "Blake", "Charlie", "Dakota", "Emerson", "Hayden", "Jesse", "Kendall", "Logan",
    "Micah", "Nico", "Parker", "Reese", "Rowan", "Ryan", "Sam", "Shiloh",
    "Spencer", "Sydney", "Tatum", "Teagan", "Zion", "Adrian", "Bailey", "Blair",
    "Brooklyn", "Carter", "Dana", "Devon", "Ellis", "Frankie", "Harper", "Indigo",
    "Kai", "Lane", "Marley", "Nevada", "Ocean", "Perry", "Quinn", "Rory", "Scout"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Walker", "Hall",
    "Allen", "Young", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Flores", "Green", "Adams", "Nelson", "Baker", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
    "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Murphy", "Cook"
]

def generate_person_name() -> str:
    """Generate a unique random name."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return f"{first} {last}"

def generate_email(name: str) -> str:
    """Generate email from name."""
    parts = name.lower().split()
    return f"{parts[0]}.{parts[1]}@company.com"

def generate_github_username(name: str) -> str:
    """Generate GitHub username from name."""
    parts = name.lower().split()
    return f"{parts[0]}{parts[1][0]}"

def generate_jira_username(name: str) -> str:
    """Generate Jira username from name (same as email prefix)."""
    parts = name.lower().split()
    return f"{parts[0]}.{parts[1]}"

def generate_person_id(name: str) -> str:
    """Generate unique person ID."""
    parts = name.lower().split()
    return f"person_{parts[0]}_{parts[1]}"

def generate_hire_date(seniority: str) -> str:
    """Generate realistic hire date based on seniority."""
    today = datetime(2026, 1, 8)
    
    # More senior = hired longer ago
    if "Junior" in seniority:
        days_ago = random.randint(90, 365)  # 3-12 months
    elif "Staff" in seniority:
        days_ago = random.randint(1095, 2555)  # 3-7 years
    elif "Senior" in seniority:
        days_ago = random.randint(730, 1825)  # 2-5 years
    else:  # Mid-level
        days_ago = random.randint(365, 1095)  # 1-3 years
    
    hire_date = today - timedelta(days=days_ago)
    return hire_date.strftime("%Y-%m-%d")

# Global set to track all used names across all person types
_used_names = set()

def generate_engineers() -> List[Dict[str, Any]]:
    """Generate all engineer nodes."""
    engineers = []
    
    for title, count in ENGINEER_DISTRIBUTION.items():
        for _ in range(count):
            # Generate unique name
            while True:
                name = generate_person_name()
                if name not in _used_names:
                    _used_names.add(name)
                    break
            
            seniority = title.replace(" Software Engineer", "").strip()
            if not seniority:
                seniority = "Mid"
            
            person = {
                "id": generate_person_id(name),
                "name": name,
                "email": generate_email(name),
                "title": title,
                "role": "Engineer",
                "seniority": seniority,
                "hire_date": generate_hire_date(seniority),
                "is_manager": False,
                "url": f"https://github.com/{generate_github_username(name)}"
            }
            engineers.append(person)
    
    return engineers

def generate_managers() -> List[Dict[str, Any]]:
    """Generate engineering manager nodes (one per team)."""
    managers = []
    
    for i in range(5):
        # Generate unique name
        while True:
            name = generate_person_name()
            if name not in _used_names:
                _used_names.add(name)
                break
        
        manager = {
            "id": generate_person_id(name),
            "name": name,
            "email": generate_email(name),
            "title": "Engineering Manager",
            "role": "Manager",
            "seniority": "Manager",
            "hire_date": generate_hire_date("Senior"),
            "is_manager": True,
            "url": f"https://github.com/{generate_github_username(name)}"
        }
        managers.append(manager)
    
    return managers

def generate_pms() -> List[Dict[str, Any]]:
    """Generate product manager nodes."""
    pms = []
    
    for i in range(2):
        while True:
            name = generate_person_name()
            if name not in _used_names:
                _used_names.add(name)
                break
        
        pm = {
            "id": generate_person_id(name),
            "name": name,
            "email": generate_email(name),
            "title": "Senior Product Manager" if i == 0 else "Product Manager",
            "role": "Product Manager",
            "seniority": "Senior" if i == 0 else "Mid",
            "hire_date": generate_hire_date("Senior" if i == 0 else "Mid"),
            "is_manager": False,
            "url": f"https://github.com/{generate_github_username(name)}"
        }
        pms.append(pm)
    
    return pms

def generate_teams() -> List[Dict[str, Any]]:
    """Generate team nodes."""
    teams = []
    
    for i, team_config in enumerate(TEAMS):
        team_slug = team_config['name'].lower().replace(' ', '_').replace('team', '').strip('_')
        team = {
            "id": f"team_{team_config['name'].lower().replace(' ', '_')}",
            "name": team_config['name'],
            "target_size": team_config['size'],
            "created_at": "2024-01-01",
            "url": f"https://github.com/orgs/company/teams/{team_slug}"
        }
        teams.append(team)
    
    return teams

def generate_identity_mappings(all_people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate identity mappings for GitHub and Jira."""
    mappings = []
    
    # Use a fixed timestamp for simulation data consistency
    simulation_timestamp = datetime.now().isoformat()
    
    for person in all_people:
        # GitHub mapping
        github_mapping = {
            "id": f"identity_github_{person['id']}",
            "provider": "GitHub",
            "username": generate_github_username(person['name']),
            "email": person['email'],
            "person_id": person['id'],
            "last_updated_at": simulation_timestamp
        }
        mappings.append(github_mapping)
        
        # Jira mapping
        jira_mapping = {
            "id": f"identity_jira_{person['id']}",
            "provider": "Jira",
            "username": generate_jira_username(person['name']),
            "email": person['email'],
            "person_id": person['id'],
            "last_updated_at": simulation_timestamp
        }
        mappings.append(jira_mapping)
    
    return mappings

def assign_people_to_teams(engineers: List[Dict[str, Any]], 
                          managers: List[Dict[str, Any]],
                          teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create MEMBER_OF relationships."""
    relationships = []
    engineer_pool = engineers.copy()
    random.shuffle(engineer_pool)
    
    current_index = 0
    
    for i, team in enumerate(teams):
        team_size = team['target_size']
        manager = managers[i]
        
        # Manager is member of team (but also manages it)
        relationships.append({
            "type": "MEMBER_OF",
            "from_id": manager['id'],
            "to_id": team['id'],
            "from_type": "Person",
            "to_type": "Team"
        })
        
        # Assign engineers to team (team_size - 1 because manager counts)
        for j in range(team_size - 1):
            if current_index < len(engineer_pool):
                engineer = engineer_pool[current_index]
                relationships.append({
                    "type": "MEMBER_OF",
                    "from_id": engineer['id'],
                    "to_id": team['id'],
                    "from_type": "Person",
                    "to_type": "Team"
                })
                current_index += 1
    
    return relationships

def create_reporting_structure(engineers: List[Dict[str, Any]], 
                              managers: List[Dict[str, Any]],
                              pms: List[Dict[str, Any]],
                              teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create REPORTS_TO relationships."""
    relationships = []
    
    # Build team to manager mapping
    team_managers = {team['id']: managers[i] for i, team in enumerate(teams)}
    
    # Engineers report to their team's manager
    for engineer in engineers:
        # Find which team this engineer is in (from MEMBER_OF relationships)
        for team in teams:
            team_size = team['target_size']
            # This is simplified - in real code we'd check the MEMBER_OF relationships
            # For now, just distribute evenly
            
    
    # Create a mapping based on team assignments
    engineer_pool = engineers.copy()
    random.shuffle(engineer_pool)
    current_index = 0
    
    for i, team in enumerate(teams):
        manager = managers[i]
        team_size = team['target_size'] - 1  # Minus manager
        
        for j in range(team_size):
            if current_index < len(engineer_pool):
                engineer = engineer_pool[current_index]
                relationships.append({
                    "type": "REPORTS_TO",
                    "from_id": engineer['id'],
                    "to_id": manager['id'],
                    "from_type": "Person",
                    "to_type": "Person"
                })
                current_index += 1
    
    # PMs report to the first manager (simplified - could be VP of Product)
    for pm in pms:
        relationships.append({
            "type": "REPORTS_TO",
            "from_id": pm['id'],
            "to_id": managers[0]['id'],
            "from_type": "Person",
            "to_type": "Person"
        })
    
    # Managers all report to a fictional VP (we won't create this node in Layer 1)
    # but we could add it later
    
    return relationships

def create_manages_relationships(managers: List[Dict[str, Any]], 
                                teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create MANAGES relationships."""
    relationships = []
    
    for i, manager in enumerate(managers):
        team = teams[i]
        relationships.append({
            "type": "MANAGES",
            "from_id": manager['id'],
            "to_id": team['id'],
            "from_type": "Person",
            "to_type": "Team"
        })
    
    return relationships

def create_identity_relationships(mappings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create MAPS_TO relationships."""
    relationships = []
    
    for mapping in mappings:
        relationships.append({
            "type": "MAPS_TO",
            "from_id": mapping['id'],
            "to_id": mapping['person_id'],
            "from_type": "IdentityMapping",
            "to_type": "Person"
        })
    
    return relationships

def main():
    """Generate all Layer 1 data."""
    print("Generating Layer 1: People & Teams Foundation")
    print("=" * 60)
    
    # Generate nodes
    print("\n1. Generating people...")
    engineers = generate_engineers()
    managers = generate_managers()
    pms = generate_pms()
    all_people = engineers + managers + pms
    print(f"   ✓ Created {len(engineers)} engineers")
    print(f"   ✓ Created {len(managers)} managers")
    print(f"   ✓ Created {len(pms)} product managers")
    print(f"   Total: {len(all_people)} people")
    
    print("\n2. Generating teams...")
    teams = generate_teams()
    print(f"   ✓ Created {len(teams)} teams")
    
    print("\n3. Generating identity mappings...")
    identity_mappings = generate_identity_mappings(all_people)
    print(f"   ✓ Created {len(identity_mappings)} identity mappings")
    
    # Generate relationships
    print("\n4. Creating relationships...")
    member_of_rels = assign_people_to_teams(engineers, managers, teams)
    reports_to_rels = create_reporting_structure(engineers, managers, pms, teams)
    manages_rels = create_manages_relationships(managers, teams)
    maps_to_rels = create_identity_relationships(identity_mappings)
    
    all_relationships = member_of_rels + reports_to_rels + manages_rels + maps_to_rels
    print(f"   ✓ MEMBER_OF: {len(member_of_rels)}")
    print(f"   ✓ REPORTS_TO: {len(reports_to_rels)}")
    print(f"   ✓ MANAGES: {len(manages_rels)}")
    print(f"   ✓ MAPS_TO: {len(maps_to_rels)}")
    print(f"   Total: {len(all_relationships)} relationships")
    
    # Create output structure
    output = {
        "metadata": {
            "layer": "Layer 1",
            "description": "People & Teams Foundation",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1"
        },
        "nodes": {
            "people": all_people,
            "teams": teams,
            "identity_mappings": identity_mappings
        },
        "relationships": all_relationships,
        "statistics": {
            "total_people": len(all_people),
            "engineers": len(engineers),
            "managers": len(managers),
            "product_managers": len(pms),
            "teams": len(teams),
            "identity_mappings": len(identity_mappings),
            "relationships": len(all_relationships)
        }
    }
    
    # Write to file
    output_path = "../data/layer1_people_teams.json"
    print(f"\n5. Writing to {output_path}...")
    with open(output_path, 'w', 
               encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print("   ✓ Data written successfully")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Nodes: {len(all_people) + len(teams) + len(identity_mappings)}")
    print(f"  - People: {len(all_people)}")
    print(f"  - Teams: {len(teams)}")
    print(f"  - Identity Mappings: {len(identity_mappings)}")
    print(f"\nTotal Relationships: {len(all_relationships)}")
    print(f"\nOutput file: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
