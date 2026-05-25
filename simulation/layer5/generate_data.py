"""
Layer 5 Data Generation: Git Repositories
Generates repository nodes with COLLABORATOR relationships (people and teams).
"""

import json
import random
from datetime import datetime
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

# Fixed sync timestamp for deterministic simulation metadata
SIMULATION_SYNCED_AT = "2026-01-15T12:00:00+00:00"
# Repository definitions
REPOSITORIES = [
    {
        "id": "repo_k8s_infrastructure",
        "name": "k8s-infrastructure",
        "full_name": "company/k8s-infrastructure",
        "url": "https://github.com/company/k8s-infrastructure",
        "language": "YAML",
        "is_private": True,
        "description": "Kubernetes infrastructure and deployment configurations",
        "topics": ["kubernetes", "infrastructure", "devops", "k8s"],
        "created_at": "2024-01-15",
        "owning_team": "team_platform_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_service_mesh",
        "name": "service-mesh",
        "full_name": "company/service-mesh",
        "url": "https://github.com/company/service-mesh",
        "language": "Go",
        "is_private": True,
        "description": "Service mesh configuration and tooling for Istio",
        "topics": ["istio", "service-mesh", "microservices", "go"],
        "created_at": "2024-02-01",
        "owning_team": "team_platform_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_api_gateway",
        "name": "gateway",
        "full_name": "company/gateway",
        "url": "https://github.com/company/gateway",
        "language": "Python",
        "is_private": True,
        "description": "API gateway service with authentication and routing",
        "topics": ["api", "gateway", "python", "microservices"],
        "created_at": "2023-11-10",
        "owning_team": "team_api_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_user_service",
        "name": "user-service",
        "full_name": "company/user-service",
        "url": "https://github.com/company/user-service",
        "language": "Python",
        "is_private": True,
        "description": "User management and authentication microservice",
        "topics": ["microservices", "api", "python", "authentication"],
        "created_at": "2023-10-05",
        "owning_team": "team_api_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_order_service",
        "name": "order-service",
        "full_name": "company/order-service",
        "url": "https://github.com/company/order-service",
        "language": "Python",
        "is_private": True,
        "description": "Order processing and management service",
        "topics": ["microservices", "api", "python", "orders"],
        "created_at": "2023-09-20",
        "owning_team": "team_api_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_web_app",
        "name": "web-app",
        "full_name": "company/web-app",
        "url": "https://github.com/company/web-app",
        "language": "TypeScript",
        "is_private": True,
        "description": "Customer-facing web application built with React",
        "topics": ["react", "typescript", "frontend", "web"],
        "created_at": "2023-08-01",
        "owning_team": "team_frontend_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_ios_app",
        "name": "ios-app",
        "full_name": "company/ios-app",
        "url": "https://github.com/company/ios-app",
        "language": "Swift",
        "is_private": True,
        "description": "iOS mobile application",
        "topics": ["ios", "swift", "mobile", "app"],
        "created_at": "2023-07-15",
        "owning_team": "team_mobile_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    },
    {
        "id": "repo_streaming_pipeline",
        "name": "streaming-pipeline",
        "full_name": "company/streaming-pipeline",
        "url": "https://github.com/company/streaming-pipeline",
        "language": "Python",
        "is_private": True,
        "description": "Real-time data streaming pipeline with Kafka and Flink",
        "topics": ["data", "streaming", "kafka", "flink", "python"],
        "created_at": "2024-03-01",
        "owning_team": "team_data_team",
        "_last_synced_at": SIMULATION_SYNCED_AT
    }
]

def load_layer1_data() -> Dict[str, Any]:
    """Load Layer 1 data to get people and teams."""
    with open('../data/layer1_people_teams.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_team_members(team_id: str, layer1_data: Dict) -> List[str]:
    """Get all person IDs that are members of a team."""
    members = []
    for rel in layer1_data['relationships']:
        if rel['type'] == 'MEMBER_OF' and rel['to_id'] == team_id:
            members.append(rel['from_id'])
    return members

def get_senior_members(person_ids: List[str], layer1_data: Dict) -> List[str]:
    """Filter for senior/staff engineers from a list of person IDs."""
    senior_people = []
    for person in layer1_data['nodes']['people']:
        if person['id'] in person_ids and person['seniority'] in ['Senior', 'Staff']:
            senior_people.append(person['id'])
    return senior_people

def get_other_teams(current_team: str) -> List[str]:
    """Get other teams for cross-team READ access."""
    all_teams = ['team_platform_team', 'team_api_team', 'team_frontend_team', 
                 'team_mobile_team', 'team_data_team']
    return [t for t in all_teams if t != current_team]

def generate_collaborator_relationships(repos: List[Dict], layer1_data: Dict) -> List[Dict]:
    """Generate COLLABORATOR relationships for repositories."""
    relationships = []
    
    for repo in repos:
        owning_team = repo['owning_team']
        team_members = get_team_members(owning_team, layer1_data)
        senior_members = get_senior_members(team_members, layer1_data)
        
        # 1. Owning team gets WRITE access
        relationships.append({
            "type": "COLLABORATOR",
            "from_id": owning_team,
            "to_id": repo['id'],
            "from_type": "Team",
            "to_type": "Repository",
            "properties": {
                "permission": "WRITE",
                "granted_at": repo['created_at']
            }
        })
        
        # 2. Select 2-3 senior members from owning team for individual WRITE access
        num_maintainers = min(len(senior_members), random.randint(2, 3))
        maintainers = random.sample(senior_members, num_maintainers) if senior_members else []
        
        for person_id in maintainers:
            relationships.append({
                "type": "COLLABORATOR",
                "from_id": person_id,
                "to_id": repo['id'],
                "from_type": "Person",
                "to_type": "Repository",
                "properties": {
                    "permission": "WRITE",
                    "role": "maintainer",
                    "granted_at": repo['created_at']
                }
            })
        
        # 3. Cross-team READ access (1-2 other teams)
        other_teams = get_other_teams(owning_team)
        num_read_teams = random.randint(0, 2)  # Some repos may have no cross-team access
        
        if num_read_teams > 0 and other_teams:
            read_teams = random.sample(other_teams, min(num_read_teams, len(other_teams)))
            for team_id in read_teams:
                relationships.append({
                    "type": "COLLABORATOR",
                    "from_id": team_id,
                    "to_id": repo['id'],
                    "from_type": "Team",
                    "to_type": "Repository",
                    "properties": {
                        "permission": "READ",
                        "reason": "cross-team dependency",
                        "granted_at": repo['created_at']
                    }
                })
        
        # 4. Individual READ access from other teams (3-5 people)
        # Get members from teams with READ access
        individual_readers = []
        for team_rel in [r for r in relationships if r['type'] == 'COLLABORATOR' 
                        and r['to_id'] == repo['id'] 
                        and r.get('properties', {}).get('permission') == 'READ'
                        and r['from_type'] == 'Team']:
            team_members = get_team_members(team_rel['from_id'], layer1_data)
            individual_readers.extend(team_members)
        
        # Add some random individuals for READ access
        if individual_readers:
            num_readers = min(len(individual_readers), random.randint(3, 5))
            selected_readers = random.sample(individual_readers, num_readers)
            
            for person_id in selected_readers:
                relationships.append({
                    "type": "COLLABORATOR",
                    "from_id": person_id,
                    "to_id": repo['id'],
                    "from_type": "Person",
                    "to_type": "Repository",
                    "properties": {
                        "permission": "READ",
                        "reason": "occasional contributor",
                        "granted_at": repo['created_at']
                    }
                })
    
    return relationships

def generate_layer5_data() -> Dict[str, Any]:
    """Generate Layer 5 repository data with collaborator relationships."""
    print("Loading Layer 1 data...")
    layer1_data = load_layer1_data()
    
    print("Generating repository collaborator relationships...")
    relationships = generate_collaborator_relationships(REPOSITORIES, layer1_data)
    
    # Prepare repository nodes (without owning_team which is implementation detail)
    repo_nodes = []
    for repo in REPOSITORIES:
        repo_node = {k: v for k, v in repo.items() if k != 'owning_team'}
        repo_nodes.append(repo_node)
    
    data = {
        "metadata": {
            "layer": "Layer 5",
            "description": "Git Repositories with Collaborator Relationships",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1"
        },
        "nodes": {
            "repositories": repo_nodes
        },
        "relationships": relationships,
        "statistics": {
            "total_repositories": len(repo_nodes),
            "total_collaborator_relationships": len(relationships),
            "team_write_access": len([r for r in relationships if r['from_type'] == 'Team' 
                                      and r.get('properties', {}).get('permission') == 'WRITE']),
            "person_write_access": len([r for r in relationships if r['from_type'] == 'Person' 
                                       and r.get('properties', {}).get('permission') == 'WRITE']),
            "team_read_access": len([r for r in relationships if r['from_type'] == 'Team' 
                                    and r.get('properties', {}).get('permission') == 'READ']),
            "person_read_access": len([r for r in relationships if r['from_type'] == 'Person' 
                                      and r.get('properties', {}).get('permission') == 'READ'])
        }
    }
    
    return data

def main():
    print("=" * 60)
    print("Layer 5: Git Repositories Data Generation")
    print("=" * 60)
    
    data = generate_layer5_data()
    
    # Save to file
    output_file = '../data/layer5_repositories.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✓ Generated {data['statistics']['total_repositories']} repositories")
    print(f"✓ Generated {data['statistics']['total_collaborator_relationships']} collaborator relationships")
    print(f"  - Team WRITE access: {data['statistics']['team_write_access']}")
    print(f"  - Person WRITE access: {data['statistics']['person_write_access']}")
    print(f"  - Team READ access: {data['statistics']['team_read_access']}")
    print(f"  - Person READ access: {data['statistics']['person_read_access']}")
    print(f"\n✓ Data saved to: {output_file}")
    print("\nNext step: Run load_to_neo4j.py to load this data into Neo4j")

if __name__ == "__main__":
    main()
