"""
Layer 6 Data Generation: Git Branches
Generates branch nodes with realistic branching patterns.
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Seed for reproducibility
random.seed(42)

def load_layer5_data() -> Dict[str, Any]:
    """Load Layer 5 data to get repositories."""
    with open('../data/layer5_repositories.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def load_layer3_data() -> Dict[str, Any]:
    """Load Layer 3 data to get epics for branch naming."""
    with open('../data/layer3_epics.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_branch_name(epic_key: str, branch_type: str, description: str) -> str:
    """Generate a realistic branch name."""
    desc_slug = description.lower().replace(' ', '-')[:30]
    return f"{branch_type}/{epic_key}-{desc_slug}"

def generate_branches_for_repo(repo: Dict, epics: List[Dict]) -> List[Dict]:
    """Generate branches for a single repository."""
    branches = []
    repo_id = repo['id']
    repo_name = repo['name']
    
    # 1. Create main branch (always exists, protected)
    main_branch = {
        "id": f"branch_main_{repo_id}",
        "name": "main",
        "is_default": True,
        "is_protected": True,
        "is_deleted": False,
        "is_external": False,
        "last_commit_sha": f"abc{random.randint(1000, 9999)}def",
        "last_commit_timestamp": datetime.now().isoformat(),
        "repository_id": repo_id
    }
    branches.append(main_branch)
    
    # 2. Create feature branches (3-5 per repo)
    num_feature_branches = random.randint(3, 5)
    
    # Select random epics for this repo's branches
    selected_epics = random.sample(epics, min(num_feature_branches, len(epics)))
    
    for i, epic in enumerate(selected_epics):
        epic_key = epic['key']
        
        # Determine branch type
        branch_types = ['feature', 'feature', 'feature', 'bugfix']  # More features than bugfixes
        branch_type = random.choice(branch_types)
        
        # Generate description
        descriptions = [
            'implement-core-logic',
            'add-api-endpoints',
            'update-configuration',
            'refactor-service',
            'add-tests',
            'fix-memory-leak',
            'optimize-performance'
        ]
        description = random.choice(descriptions)
        
        branch_name = generate_branch_name(epic_key, branch_type, description)
        
        # Determine if branch is deleted (merged and cleaned up)
        # About 30% of branches are deleted (already merged)
        is_deleted = random.random() < 0.3
        
        # Calculate last commit timestamp (some branches are stale)
        if is_deleted:
            # Deleted branches have older last commits
            days_ago = random.randint(15, 60)
        else:
            # Active branches have more recent activity
            # But some are stale (>30 days)
            days_ago = random.randint(1, 45)
        
        last_commit_time = datetime.now() - timedelta(days=days_ago)
        
        branch = {
            "id": f"branch_{repo_id}_{i}",
            "name": branch_name,
            "is_default": False,
            "is_protected": False,
            "is_deleted": is_deleted,
            "last_commit_sha": f"xyz{random.randint(1000, 9999)}abc",
            "last_commit_timestamp": last_commit_time.isoformat(),
            "repository_id": repo_id
        }
        branches.append(branch)
    
    return branches

def generate_layer6_data() -> Dict[str, Any]:
    """Generate Layer 6 branch data."""
    print("Loading Layer 5 data (repositories)...")
    layer5_data = load_layer5_data()
    repositories = layer5_data['nodes']['repositories']
    
    print("Loading Layer 3 data (epics)...")
    layer3_data = load_layer3_data()
    epics = layer3_data['nodes']['epics']
    
    print("Generating branches for each repository...")
    all_branches = []
    
    for repo in repositories:
        repo_branches = generate_branches_for_repo(repo, epics)
        all_branches.extend(repo_branches)
        print(f"  ✓ Generated {len(repo_branches)} branches for {repo['name']}")
    
    # Generate BRANCH_OF relationships
    relationships = []
    for branch in all_branches:
        relationships.append({
            "type": "BRANCH_OF",
            "from_id": branch['id'],
            "to_id": branch['repository_id'],
            "from_type": "Branch",
            "to_type": "Repository"
        })
    
    # Remove repository_id from branch nodes (it's only for relationship creation)
    for branch in all_branches:
        del branch['repository_id']
    
    data = {
        "metadata": {
            "layer": "Layer 6",
            "description": "Git Branches",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1"
        },
        "nodes": {
            "branches": all_branches
        },
        "relationships": relationships,
        "statistics": {
            "total_branches": len(all_branches),
            "default_branches": len([b for b in all_branches if b['is_default']]),
            "feature_branches": len([b for b in all_branches if not b['is_default']]),
            "deleted_branches": len([b for b in all_branches if b['is_deleted']]),
            "active_branches": len([b for b in all_branches if not b['is_deleted'] and not b['is_default']]),
            "protected_branches": len([b for b in all_branches if b['is_protected']])
        }
    }
    
    return data

def main():
    print("=" * 60)
    print("Layer 6: Git Branches Data Generation")
    print("=" * 60)
    
    data = generate_layer6_data()
    
    # Save to file
    output_file = '../data/layer6_branches.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✓ Generated {data['statistics']['total_branches']} branches")
    print(f"  - Default branches: {data['statistics']['default_branches']}")
    print(f"  - Feature branches: {data['statistics']['feature_branches']}")
    print(f"  - Active branches: {data['statistics']['active_branches']}")
    print(f"  - Deleted branches: {data['statistics']['deleted_branches']}")
    print(f"  - Protected branches: {data['statistics']['protected_branches']}")
    print(f"\n✓ Data saved to: {output_file}")
    print("\nNext step: Run load_to_neo4j.py to load this data into Neo4j")

if __name__ == "__main__":
    main()
