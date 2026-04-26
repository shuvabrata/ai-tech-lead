"""
Layer 3 Data Generation: Jira Epics
Generates epics that break down initiatives into actionable work items.
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

# Fixed sync timestamp for deterministic simulation metadata
SIMULATION_SYNCED_AT = "2026-01-15T12:00:00+00:00"
# Epic definitions aligned with initiatives
EPICS = {
    "initiative_init_1": [  # Platform Modernization
        {
            "key": "PLAT-1",
            "summary": "Migrate to Kubernetes",
            "description": "Migrate existing services from VMs to Kubernetes clusters with proper service discovery and configuration management",
            "priority": "High",
            "status": "In Progress"
        },
        {
            "key": "PLAT-2",
            "summary": "Implement Service Mesh",
            "description": "Deploy Istio service mesh for traffic management, observability, and security",
            "priority": "High",
            "status": "In Progress"
        },
        {
            "key": "PLAT-3",
            "summary": "Observability Stack Upgrade",
            "description": "Upgrade monitoring stack with Prometheus, Grafana, and distributed tracing",
            "priority": "Medium",
            "status": "Planning"
        },
        {
            "key": "PLAT-4",
            "summary": "CI/CD Pipeline Rewrite",
            "description": "Modernize CI/CD pipelines with GitOps practices and automated deployment",
            "priority": "High",
            "status": "In Progress"
        }
    ],
    "initiative_init_2": [  # Customer Portal Rebuild
        {
            "key": "PORT-1",
            "summary": "Authentication & Authorization",
            "description": "Implement modern OAuth2/OIDC authentication with role-based access control",
            "priority": "Critical",
            "status": "In Progress"
        },
        {
            "key": "PORT-2",
            "summary": "Dashboard UI Components",
            "description": "Build reusable React component library for dashboard features",
            "priority": "High",
            "status": "In Progress"
        },
        {
            "key": "PORT-3",
            "summary": "API Gateway Layer",
            "description": "Create unified API gateway for customer-facing services",
            "priority": "High",
            "status": "Planning"
        },
        {
            "key": "PORT-4",
            "summary": "Mobile Responsive Design",
            "description": "Ensure full mobile responsiveness across all portal features",
            "priority": "Medium",
            "status": "To Do"
        },
        {
            "key": "PORT-5",
            "summary": "Analytics Integration",
            "description": "Integrate analytics tracking and user behavior monitoring",
            "priority": "Medium",
            "status": "To Do"
        }
    ],
    "initiative_init_3": [  # Data Pipeline v2
        {
            "key": "DATA-1",
            "summary": "Streaming Architecture",
            "description": "Build Kafka-based streaming data pipeline with real-time processing",
            "priority": "Critical",
            "status": "In Progress"
        },
        {
            "key": "DATA-2",
            "summary": "Data Warehouse Migration",
            "description": "Migrate from legacy data warehouse to modern cloud-based solution",
            "priority": "High",
            "status": "Planning"
        },
        {
            "key": "DATA-3",
            "summary": "Real-time Analytics Engine",
            "description": "Build real-time analytics processing engine for customer insights",
            "priority": "High",
            "status": "Planning"
        }
    ]
}

# Team assignments for each epic (based on epic domain)
EPIC_TEAM_MAPPING = {
    "PLAT-1": "team_platform_team",
    "PLAT-2": "team_platform_team",
    "PLAT-3": "team_platform_team",
    "PLAT-4": "team_platform_team",
    "PORT-1": "team_api_team",
    "PORT-2": "team_frontend_team",
    "PORT-3": "team_api_team",
    "PORT-4": "team_frontend_team",
    "PORT-5": "team_frontend_team",
    "DATA-1": "team_data_team",
    "DATA-2": "team_data_team",
    "DATA-3": "team_data_team"
}

def load_layer1_data() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load people and teams from Layer 1."""
    with open("../data/layer1_people_teams.json", 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['nodes']['people'], data['nodes']['teams']

def load_layer2_data() -> List[Dict[str, Any]]:
    """Load initiatives from Layer 2."""
    with open("../data/layer2_initiatives.json", 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['nodes']['initiatives']

def get_potential_epic_owners(people: List[Dict[str, Any]], team_id: str) -> List[Dict[str, Any]]:
    """Get people who can own epics (Senior/Staff engineers and PMs from specific team)."""
    owners = []
    
    # Load team memberships from Layer 1
    with open("../data/layer1_people_teams.json", 'r', encoding='utf-8') as f:
        layer1_data = json.load(f)
    
    # Build person-to-team mapping
    person_to_team = {}
    for rel in layer1_data['relationships']:
        if rel['type'] == 'MEMBER_OF' and rel['from_type'] == 'Person':
            person_to_team[rel['from_id']] = rel['to_id']
    
    for person in people:
        # PMs can own any epic
        if person['role'] == 'Product Manager':
            owners.append(person)
        # Senior/Staff engineers from the specific team
        elif person['role'] == 'Engineer' and person['seniority'] in ['Senior', 'Staff']:
            if person_to_team.get(person['id']) == team_id:
                owners.append(person)
    
    return owners

def calculate_epic_dates(initiative: Dict[str, Any], epic_index: int, total_epics: int) -> tuple[str, str]:
    """Calculate start and due dates for epic based on initiative timeline."""
    init_start = datetime.strptime(initiative['created_at'], "%Y-%m-%d")
    init_end = datetime.strptime(initiative['duedate'], "%Y-%m-%d")
    
    total_days = (init_end - init_start).days
    epic_duration = total_days // total_epics
    
    # Add some overlap - epics can run in parallel
    start_offset = (epic_index * epic_duration) // 2
    epic_start = init_start + timedelta(days=start_offset)
    epic_end = epic_start + timedelta(days=epic_duration + 30)  # Longer than slot for overlap
    
    # Ensure epic end doesn't exceed initiative end
    if epic_end > init_end:
        epic_end = init_end
    
    return epic_start.strftime("%Y-%m-%d"), epic_end.strftime("%Y-%m-%d")

def generate_epics(initiatives: List[Dict[str, Any]], 
                   people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate Epic nodes with owners and teams."""
    all_epics = []
    
    for initiative in initiatives:
        epic_defs = EPICS.get(initiative['id'], [])
        
        for idx, epic_def in enumerate(epic_defs):
            team_id = EPIC_TEAM_MAPPING[epic_def['key']]
            potential_owners = get_potential_epic_owners(people, team_id)
            
            # Assign random owner from potential pool
            if potential_owners:
                owner = random.choice(potential_owners)
            else:
                # Fallback to any Senior/Staff or PM
                fallback_owners = [p for p in people 
                                 if (p['role'] == 'Product Manager' or 
                                     (p['role'] == 'Engineer' and p['seniority'] in ['Senior', 'Staff']))]
                owner = random.choice(fallback_owners)
            
            start_date, due_date = calculate_epic_dates(initiative, idx, len(epic_defs))
            
            epic = {
                "id": f"epic_{epic_def['key'].lower().replace('-', '_')}",
                "key": epic_def['key'],
                "summary": epic_def['summary'],
                "priority": epic_def['priority'],
                "status": epic_def['status'],
                "start_date": start_date,
                "due_date": due_date,
                "created_at": "2025-11-15",
                "updated_at": "2025-11-15",
                "initiative_id": initiative['id'],
                "assignee_id": owner['id'],
                "team_id": team_id,
                "url": f"https://yoursite.atlassian.net/browse/{epic_def['key']}",
                "_last_synced_at": SIMULATION_SYNCED_AT
            }
            all_epics.append(epic)
    
    return all_epics

def create_part_of_relationships(epics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create PART_OF relationships: Epic → Initiative."""
    relationships = []
    
    for epic in epics:
        relationships.append({
            "type": "PART_OF",
            "from_id": epic['id'],
            "to_id": epic['initiative_id'],
            "from_type": "Epic",
            "to_type": "Initiative"
        })
    
    return relationships

def create_assigned_to_relationships(epics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create ASSIGNED_TO relationships: Epic ↔ Person (undirected)."""
    relationships = []
    
    for epic in epics:
        relationships.append({
            "type": "ASSIGNED_TO",
            "from_id": epic['id'],
            "to_id": epic['assignee_id'],
            "from_type": "Epic",
            "to_type": "Person"
        })
    
    return relationships

def create_team_relationships(epics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create TEAM relationships: Epic ↔ Team (undirected)."""
    relationships = []
    
    for epic in epics:
        relationships.append({
            "type": "TEAM",
            "from_id": epic['id'],
            "to_id": epic['team_id'],
            "from_type": "Epic",
            "to_type": "Team"
        })
    
    return relationships

def main():
    """Generate all Layer 3 data."""
    print("Generating Layer 3: Jira Epics")
    print("=" * 60)
    
    # Load Layer 1 and Layer 2 data
    print("\n1. Loading Layer 1 and Layer 2 data...")
    people, teams = load_layer1_data()
    initiatives = load_layer2_data()
    print(f"   ✓ Loaded {len(people)} people")
    print(f"   ✓ Loaded {len(teams)} teams")
    print(f"   ✓ Loaded {len(initiatives)} initiatives")
    
    # Generate epics
    print("\n2. Generating epics...")
    epics = generate_epics(initiatives, people)
    print(f"   ✓ Created {len(epics)} epics:")
    
    # Group by initiative for display
    epics_by_initiative = {}
    for epic in epics:
        init_id = epic['initiative_id']
        if init_id not in epics_by_initiative:
            epics_by_initiative[init_id] = []
        epics_by_initiative[init_id].append(epic)
    
    for init in initiatives:
        print(f"\n   {init['summary']}:")
        for epic in epics_by_initiative.get(init['id'], []):
            owner = next(p for p in people if p['id'] == epic['assignee_id'])
            team = next(t for t in teams if t['id'] == epic['team_id'])
            print(f"      - {epic['key']}: {epic['summary']}")
            print(f"        Owner: {owner['name']} ({owner['title']})")
            print(f"        Team: {team['name']}")
            print(f"        Timeline: {epic['start_date']} → {epic['due_date']}")
    
    # Generate relationships
    print("\n3. Creating relationships...")
    part_of_rels = create_part_of_relationships(epics)
    assigned_to_rels = create_assigned_to_relationships(epics)
    team_rels = create_team_relationships(epics)
    
    all_relationships = part_of_rels + assigned_to_rels + team_rels
    print(f"   ✓ PART_OF: {len(part_of_rels)}")
    print(f"   ✓ ASSIGNED_TO: {len(assigned_to_rels)}")
    print(f"   ✓ TEAM: {len(team_rels)}")
    print(f"   Total: {len(all_relationships)} relationships")
    
    # Create output structure
    output = {
        "metadata": {
            "layer": "Layer 3",
            "description": "Jira Epics",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1",
            "depends_on": ["layer1_people_teams.json", "layer2_initiatives.json"]
        },
        "nodes": {
            "epics": epics
        },
        "relationships": all_relationships,
        "statistics": {
            "epics": len(epics),
            "relationships": len(all_relationships)
        }
    }
    
    # Write to file
    output_path = "../data/layer3_epics.json"
    print(f"\n4. Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print("   ✓ Data written successfully")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Nodes: {len(epics)}")
    print(f"  - Epics: {len(epics)}")
    print(f"\nTotal Relationships: {len(all_relationships)}")
    print(f"  - PART_OF: {len(part_of_rels)}")
    print(f"  - ASSIGNED_TO: {len(assigned_to_rels)}")
    print(f"  - TEAM: {len(team_rels)}")
    print(f"\nOutput file: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
