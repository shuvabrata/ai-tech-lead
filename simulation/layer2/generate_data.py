"""
Layer 2 Data Generation: Jira Initiatives
Generates high-level business initiatives and links them to people from Layer 1.
"""

import json
import random
from datetime import datetime
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

# Fixed sync timestamp for deterministic simulation metadata
SIMULATION_SYNCED_AT = "2026-01-15T12:00:00+00:00"
# Initiative definitions
INITIATIVES = [
    {
        "key": "INIT-1",
        "summary": "Platform Modernization",
        "description": "Modernize infrastructure with Kubernetes, service mesh, and improved observability",
        "start_quarter": "Q1",
        "end_quarter": "Q2",
        "priority": "High",
        "status": "In Progress"
    },
    {
        "key": "INIT-2",
        "summary": "Customer Portal Rebuild",
        "description": "Complete redesign of customer-facing portal with modern architecture",
        "start_quarter": "Q1",
        "end_quarter": "Q3",
        "priority": "Critical",
        "status": "In Progress"
    },
    {
        "key": "INIT-3",
        "summary": "Data Pipeline v2",
        "description": "Build next-generation data pipeline with streaming and real-time analytics",
        "start_quarter": "Q2",
        "end_quarter": "Q3",
        "priority": "High",
        "status": "Planning"
    }
]

def quarter_to_date(year: int, quarter: str, is_start: bool) -> str:
    """Convert quarter string to date."""
    quarter_starts = {
        "Q1": (1, 1),
        "Q2": (4, 1),
        "Q3": (7, 1),
        "Q4": (10, 1)
    }
    
    quarter_ends = {
        "Q1": (3, 31),
        "Q2": (6, 30),
        "Q3": (9, 30),
        "Q4": (12, 31)
    }
    
    if is_start:
        month, day = quarter_starts[quarter]
    else:
        month, day = quarter_ends[quarter]
    
    return datetime(year, month, day).strftime("%Y-%m-%d")

def load_layer1_people() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load people and teams data from Layer 1."""
    with open("../data/layer1_people_teams.json", 'r',encoding='utf-8') as f:
        data = json.load(f)
    return data['nodes']['people'], data['nodes']['teams']

def get_potential_assignees(people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get people who can be assigned initiatives (Staff engineers and Senior engineers)."""
    assignees = []
    
    for person in people:
        # Staff and Senior engineers can be assigned initiatives
        if person['role'] == 'Engineer' and person['seniority'] in ['Staff', 'Senior']:
            assignees.append(person)
    
    return assignees

def get_potential_reporters(people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get people who can report initiatives (PMs and Staff engineers)."""
    reporters = []
    
    for person in people:
        # Product Managers can report initiatives
        if person['role'] == 'Product Manager':
            reporters.append(person)
        # Staff engineers can also report initiatives
        elif person['role'] == 'Engineer' and person['seniority'] == 'Staff':
            reporters.append(person)
    
    return reporters

def generate_project() -> Dict[str, Any]:
    """Generate the parent Project node."""
    return {
        "id": "project_engineering_2026",
        "key": "ENG-2026",
        "name": "Engineering 2026",
        "status": "Active"
    }

def generate_initiatives(assignees: List[Dict[str, Any]], 
                        reporters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate Initiative nodes with assigned owners and reporters."""
    initiatives = []
    
    # Shuffle both lists for random assignment
    available_assignees = assignees.copy()
    available_reporters = reporters.copy()
    random.shuffle(available_assignees)
    random.shuffle(available_reporters)
    
    for i, init_def in enumerate(INITIATIVES):
        # Assign assignee and reporter (cycle through if we have fewer than initiatives)
        assignee = available_assignees[i % len(available_assignees)]
        reporter = available_reporters[i % len(available_reporters)]
        
        initiative = {
            "id": f"initiative_{init_def['key'].lower().replace('-', '_')}",
            "key": init_def['key'],
            "summary": init_def['summary'],
            "priority": init_def['priority'],
            "status": init_def['status'],
            "created_at": quarter_to_date(2026, init_def['start_quarter'], True),
            "updated_at": quarter_to_date(2026, init_def['start_quarter'], True),
            "duedate": quarter_to_date(2026, init_def['end_quarter'], False),
            "assignee_id": assignee['id'],
            "reporter_id": reporter['id'],
            "_last_synced_at": SIMULATION_SYNCED_AT
        }
        initiatives.append(initiative)
    
    return initiatives

def create_part_of_relationships(initiatives: List[Dict[str, Any]], 
                                 project: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create PART_OF relationships: Initiative → Project."""
    relationships = []
    
    for initiative in initiatives:
        relationships.append({
            "type": "PART_OF",
            "from_id": initiative['id'],
            "to_id": project['id'],
            "from_type": "Initiative",
            "to_type": "Project"
        })
    
    return relationships

def create_owned_by_relationships(initiatives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create ASSIGNED_TO relationships: Initiative ↔ Person (undirected)."""
    relationships = []
    
    for initiative in initiatives:
        relationships.append({
            "type": "ASSIGNED_TO",
            "from_id": initiative['id'],
            "to_id": initiative['assignee_id'],
            "from_type": "Initiative",
            "to_type": "Person"
        })
    
    return relationships

def create_reported_by_relationships(initiatives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create REPORTED_BY relationships: Initiative → Person."""
    relationships = []
    
    for initiative in initiatives:
        relationships.append({
            "type": "REPORTED_BY",
            "from_id": initiative['id'],
            "to_id": initiative['reporter_id'],
            "from_type": "Initiative",
            "to_type": "Person"
        })
    
    return relationships

def main():
    """Generate all Layer 2 data."""
    print("Generating Layer 2: Jira Initiatives")
    print("=" * 60)
    
    # Load Layer 1 data
    print("\n1. Loading Layer 1 data...")
    people, teams = load_layer1_people()
    print(f"   ✓ Loaded {len(people)} people")
    print(f"   ✓ Loaded {len(teams)} teams")
    
    # Load Layer 1 relationships to find person-team mappings
    with open("../data/layer1_people_teams.json", 'r', encoding='utf-8') as f:
        layer1_data = json.load(f)
    layer1_relationships = layer1_data['relationships']
    
    # Get potential assignees and reporters
    print("\n2. Identifying potential assignees and reporters...")
    assignees = get_potential_assignees(people)
    reporters = get_potential_reporters(people)
    print(f"   ✓ Found {len(assignees)} potential assignees (Senior/Staff engineers)")
    print(f"   ✓ Found {len(reporters)} potential reporters (PMs and Staff engineers)")
    
    # Generate nodes
    print("\n3. Generating project and initiatives...")
    project = generate_project()
    initiatives = generate_initiatives(assignees, reporters)
    print(f"   ✓ Created 1 project: {project['name']}")
    print(f"   ✓ Created {len(initiatives)} initiatives:")
    for init in initiatives:
        # Find assignee and reporter names
        assignee = next(p for p in people if p['id'] == init['assignee_id'])
        reporter = next(p for p in people if p['id'] == init['reporter_id'])
        print(f"      - {init['key']}: {init['summary']}")
        print(f"        Assignee: {assignee['name']} ({assignee['title']})")
        print(f"        Reporter: {reporter['name']} ({reporter['title']})")
    
    # Generate relationships
    print("\n4. Creating relationships...")
    part_of_rels = create_part_of_relationships(initiatives, project)
    assigned_to_rels = create_owned_by_relationships(initiatives)
    reported_by_rels = create_reported_by_relationships(initiatives)
    
    all_relationships = part_of_rels + assigned_to_rels + reported_by_rels
    print(f"   ✓ PART_OF: {len(part_of_rels)}")
    print(f"   ✓ ASSIGNED_TO: {len(assigned_to_rels)}")
    print(f"   ✓ REPORTED_BY: {len(reported_by_rels)}")
    print(f"   Total: {len(all_relationships)} relationships")
    
    # Create output structure
    output = {
        "metadata": {
            "layer": "Layer 2",
            "description": "Jira Initiatives",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1",
            "depends_on": ["layer1_people_teams.json"]
        },
        "nodes": {
            "project": project,
            "initiatives": initiatives
        },
        "relationships": all_relationships,
        "statistics": {
            "project": 1,
            "initiatives": len(initiatives),
            "relationships": len(all_relationships)
        }
    }
    
    # Write to file
    output_path = "../data/layer2_initiatives.json"
    print(f"\n5. Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print("   ✓ Data written successfully")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Nodes: {1 + len(initiatives)}")
    print("  - Project: 1")
    print(f"  - Initiatives: {len(initiatives)}")
    print(f"\nTotal Relationships: {len(all_relationships)}")
    print(f"  - PART_OF: {len(part_of_rels)}")
    print(f"  - ASSIGNED_TO: {len(assigned_to_rels)}")
    print(f"  - REPORTED_BY: {len(reported_by_rels)}")
    print(f"\nOutput file: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
