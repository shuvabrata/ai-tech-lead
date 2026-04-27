"""
Layer 4 Data Generation: Jira Stories & Bugs
Generates granular work items (stories, bugs, tasks) and sprints.
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# Seed for reproducibility
random.seed(42)

# Fixed sync timestamp for deterministic simulation metadata
SIMULATION_SYNCED_AT = "2026-01-15T12:00:00+00:00"
# Sprint definitions (4 sprints, 2 weeks each, covering last 2 months)
SPRINTS = [
    {
        "name": "Sprint 1",
        "start_date": "2025-12-09",
        "end_date": "2025-12-20",
        "goal": "Platform infrastructure foundations"
    },
    {
        "name": "Sprint 2",
        "start_date": "2025-12-23",
        "end_date": "2026-01-03",
        "goal": "Customer portal authentication"
    },
    {
        "name": "Sprint 3",
        "start_date": "2026-01-06",
        "end_date": "2026-01-17",
        "goal": "Data pipeline streaming components"
    },
    {
        "name": "Sprint 4",
        "start_date": "2026-01-20",
        "end_date": "2026-01-31",
        "goal": "UI components and API integration"
    }
]

# Story point distribution (Fibonacci sequence)
STORY_POINTS = [1, 2, 3, 5, 8, 13]

# Status distribution for issues
STATUS_DISTRIBUTION = {
    "Done": 0.40,
    "In Progress": 0.25,
    "To Do": 0.20,
    "In Review": 0.10,
    "Blocked": 0.05
}

# Priority distribution
PRIORITY_DISTRIBUTION = {
    "Critical": 0.10,
    "High": 0.30,
    "Medium": 0.45,
    "Low": 0.15
}

def load_previous_layers() -> Tuple[List, List, List, List]:
    """Load data from Layers 1-3."""
    # Layer 1: People and Teams
    with open("../data/layer1_people_teams.json", 'r', encoding='utf-8') as f:
        layer1 = json.load(f)
    people = layer1['nodes']['people']
    teams = layer1['nodes']['teams']
    
    # Layer 2: Initiatives
    with open("../data/layer2_initiatives.json", 'r', encoding='utf-8') as f:
        layer2 = json.load(f)
    initiatives = layer2['nodes']['initiatives']
    
    # Layer 3: Epics
    with open("../data/layer3_epics.json", 'r', encoding='utf-8') as f:
        layer3 = json.load(f)
    epics = layer3['nodes']['epics']
    
    return people, teams, initiatives, epics

def get_team_members(team_id: str, people: List[Dict], layer1_relationships: List[Dict]) -> List[Dict]:
    """Get all people who are members of a specific team."""
    team_member_ids = [
        rel['from_id'] for rel in layer1_relationships
        if rel['type'] == 'MEMBER_OF' and rel['to_id'] == team_id
    ]
    return [p for p in people if p['id'] in team_member_ids]

def weighted_choice(choices: dict) -> str:
    """Make a weighted random choice from a distribution."""
    items = list(choices.keys())
    weights = list(choices.values())
    return random.choices(items, weights=weights)[0]

def generate_sprints() -> List[Dict[str, Any]]:
    """Generate Sprint nodes."""
    sprints = []
    for idx, sprint_def in enumerate(SPRINTS, start=1):
        sprint = {
            "id": f"sprint_{idx}",
            "name": sprint_def['name'],
            "goal": sprint_def['goal'],
            "start_date": sprint_def['start_date'],
            "end_date": sprint_def['end_date'],
            "status": "Completed" if idx < 4 else "Active",
            "url": None  # Sprint URLs are complex in Jira, leaving as None
        }
        sprints.append(sprint)
    return sprints

def generate_story_for_epic(epic: Dict, epic_index: int, story_num: int,
                            team_members: List[Dict], people: List[Dict]) -> Dict[str, Any]:
    """Generate a single story for an epic."""
    epic_key = epic['key']
    story_key = f"{epic_key.split('-')[0]}-{(epic_index * 10) + story_num}"
    
    # Story templates based on epic type
    story_templates = {
        "PLAT": [
            "Implement {} infrastructure component",
            "Configure {} for production",
            "Set up {} monitoring and alerts",
            "Create {} deployment pipeline",
            "Write {} documentation",
        ],
        "PORT": [
            "Build {} UI component",
            "Implement {} form validation",
            "Add {} to user dashboard",
            "Style {} for mobile",
            "Integrate {} with backend API",
        ],
        "DATA": [
            "Design {} data schema",
            "Implement {} data processor",
            "Set up {} streaming pipeline",
            "Create {} ETL job",
            "Add {} data validation",
        ]
    }
    
    epic_type = epic_key.split('-')[0]
    template = random.choice(story_templates.get(epic_type, story_templates["PLAT"]))
    
    # Generate story summary based on epic
    components = {
        "PLAT": ["Kubernetes deployment", "service mesh config", "observability stack", "CI/CD workflow", "security policies"],
        "PORT": ["login form", "user profile", "dashboard widget", "navigation menu", "settings panel"],
        "DATA": ["event schema", "stream processor", "data warehouse table", "batch job", "data quality check"]
    }
    
    component = random.choice(components.get(epic_type, components["PLAT"]))
    summary = template.format(component)
    
    # Assign to team member or PM
    if team_members:
        assignee = random.choice(team_members)
    else:
        # Fallback to any engineer
        engineers = [p for p in people if p['role'] == 'Engineer']
        assignee = random.choice(engineers)
    
    # Reporter is usually PM or Staff engineer
    reporters = [p for p in people if p['role'] == 'Product Manager' or 
                (p['role'] == 'Engineer' and p['seniority'] == 'Staff')]
    reporter = random.choice(reporters)
    
    # Generate creation date within epic timeframe
    epic_start = datetime.strptime(epic['start_date'], "%Y-%m-%d")
    created_at = epic_start - timedelta(days=random.randint(7, 21))
    
    story = {
        "id": f"issue_{story_key.lower().replace('-', '_')}",
        "key": story_key,
        "type": "Story",
        "summary": summary,
        "priority": weighted_choice(PRIORITY_DISTRIBUTION),
        "status": weighted_choice(STATUS_DISTRIBUTION),
        "story_points": random.choice(STORY_POINTS),
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
        "epic_id": epic['id'],
        "assignee_id": assignee['id'],
        "reporter_id": reporter['id'],
        "url": f"https://yoursite.atlassian.net/browse/{story_key}",
        "_last_synced_at": SIMULATION_SYNCED_AT
    }
    
    return story

def generate_stories(epics: List[Dict], people: List[Dict], teams: List[Dict],
                     layer1_relationships: List[Dict]) -> List[Dict[str, Any]]:
    """Generate 60 stories distributed across epics."""
    stories = []
    
    # Distribute stories: 4-8 per epic (total ~60)
    stories_per_epic = [5, 5, 4, 6, 5, 5, 5, 4, 6, 5, 5, 5]  # Sums to 60
    
    for epic_idx, (epic, story_count) in enumerate(zip(epics, stories_per_epic)):
        # Get team members for this epic
        team_members = get_team_members(epic['team_id'], people, layer1_relationships)
        
        for story_num in range(1, story_count + 1):
            story = generate_story_for_epic(epic, epic_idx, story_num, team_members, people)
            stories.append(story)
    
    return stories

def generate_bugs(stories: List[Dict], people: List[Dict]) -> List[Dict[str, Any]]:
    """Generate 15 bugs (5 linked to stories, 10 standalone)."""
    bugs = []
    
    bug_templates = [
        "Memory leak in {}",
        "{} service crashing under load",
        "Incorrect {} calculation",
        "{} UI not responsive on mobile",
        "Race condition in {}",
        "Null pointer exception in {}",
        "{} failing for edge cases",
        "Performance degradation in {}",
        "Data corruption in {}",
        "{} authentication failing",
    ]
    
    # 5 bugs linked to stories (found during testing)
    story_bugs = random.sample([s for s in stories if s['status'] in ['Done', 'In Review']], 5)
    
    for idx, story in enumerate(story_bugs, start=1):
        epic_prefix = story['key'].split('-')[0]
        bug_key = f"BUG-{idx}"
        created_at_str = (datetime.fromisoformat(story['created_at']) +
                          timedelta(days=random.randint(10, 30))).isoformat()
        
        bug = {
            "id": f"issue_{bug_key.lower().replace('-', '_')}",
            "key": bug_key,
            "type": "Bug",
            "summary": f"Bug found in {story['summary']}",
            "priority": random.choice(["Critical", "High", "High", "Medium"]),
            "status": weighted_choice({"To Do": 0.3, "In Progress": 0.4, "Done": 0.3}),
            "story_points": random.choice([1, 2, 3]),
            "created_at": created_at_str,
            "updated_at": created_at_str,
            "epic_id": story['epic_id'],
            "assignee_id": story['assignee_id'],  # Same assignee as story
            "reporter_id": story['reporter_id'],
            "related_story_id": story['id'],  # Link to story
            "url": f"https://yoursite.atlassian.net/browse/{bug_key}",
            "_last_synced_at": SIMULATION_SYNCED_AT
        }
        bugs.append(bug)
    
    # 10 standalone production bugs
    for idx in range(6, 16):
        bug_key = f"BUG-{idx}"
        template = random.choice(bug_templates)
        component = random.choice(["user service", "API gateway", "data pipeline", 
                                  "UI dashboard", "authentication", "payment processor"])
        
        engineers = [p for p in people if p['role'] == 'Engineer']
        assignee = random.choice(engineers)
        
        reporters = [p for p in people if p['role'] in ['Product Manager', 'Engineering Manager']]
        reporter = random.choice(reporters)
        
        # Random epic for context
        epic = random.choice([s['epic_id'] for s in stories])
        
        created_at_str = (datetime.now() - timedelta(days=random.randint(5, 60))).isoformat()
        bug = {
            "id": f"issue_{bug_key.lower().replace('-', '_')}",
            "key": bug_key,
            "type": "Bug",
            "summary": template.format(component),
            "priority": weighted_choice(PRIORITY_DISTRIBUTION),
            "status": weighted_choice({"To Do": 0.2, "In Progress": 0.3, "Done": 0.4, "Blocked": 0.1}),
            "story_points": random.choice([1, 2, 3, 5]),
            "created_at": created_at_str,
            "updated_at": created_at_str,
            "epic_id": epic,
            "assignee_id": assignee['id'],
            "reporter_id": reporter['id'],
            "url": f"https://yoursite.atlassian.net/browse/{bug_key}",
            "_last_synced_at": SIMULATION_SYNCED_AT
        }
        bugs.append(bug)
    
    return bugs

def generate_tasks(epics: List[Dict], people: List[Dict]) -> List[Dict[str, Any]]:
    """Generate 5 technical tasks (debt, spikes)."""
    tasks = []
    
    task_templates = [
        "Technical spike: Evaluate {} options",
        "Refactor {} codebase",
        "Update {} dependencies",
        "Document {} architecture",
        "Performance optimization for {}",
    ]
    
    components = ["monitoring tools", "database layer", "API framework", 
                 "deployment process", "logging system"]
    
    for idx, (template, component) in enumerate(zip(task_templates, components), start=1):
        task_key = f"TASK-{idx}"
        
        # Tasks usually assigned to Senior/Staff engineers
        assignees = [p for p in people if p['role'] == 'Engineer' and 
                    p['seniority'] in ['Senior', 'Staff']]
        assignee = random.choice(assignees)
        
        reporters = [p for p in people if p['role'] in ['Engineering Manager', 'Product Manager']]
        reporter = random.choice(reporters)
        
        epic = random.choice(epics)
        
        created_at_str = (datetime.now() - timedelta(days=random.randint(10, 45))).isoformat()
        task = {
            "id": f"issue_{task_key.lower().replace('-', '_')}",
            "key": task_key,
            "type": "Task",
            "summary": template.format(component),
            "priority": random.choice(["Medium", "Low", "Low"]),
            "status": weighted_choice(STATUS_DISTRIBUTION),
            "story_points": random.choice([2, 3, 5, 8]),
            "created_at": created_at_str,
            "updated_at": created_at_str,
            "epic_id": epic['id'],
            "assignee_id": assignee['id'],
            "reporter_id": reporter['id'],
            "url": f"https://yoursite.atlassian.net/browse/{task_key}",
            "_last_synced_at": SIMULATION_SYNCED_AT
        }
        tasks.append(task)
    
    return tasks

def assign_issues_to_sprints(issues: List[Dict], sprints: List[Dict]) -> List[Dict[str, Any]]:
    """Create IN_SPRINT relationships."""
    relationships = []
    
    # Assign issues to sprints based on status and timing
    for issue in issues:
        # Done issues go to earlier sprints, To Do to later sprints
        if issue['status'] == 'Done':
            sprint = random.choice(sprints[:2])  # Sprint 1 or 2
        elif issue['status'] in ['In Progress', 'In Review']:
            sprint = sprints[2]  # Sprint 3
        elif issue['status'] == 'To Do':
            sprint = sprints[3]  # Sprint 4
        elif issue['status'] == 'Blocked':
            sprint = random.choice(sprints[1:3])  # Sprint 2 or 3
        else:
            sprint = random.choice(sprints)
        
        relationships.append({
            "type": "IN_SPRINT",
            "from_id": issue['id'],
            "to_id": sprint['id'],
            "from_type": "Issue",
            "to_type": "Sprint"
        })
    
    return relationships

def create_issue_dependencies(issues: List[Dict]) -> List[Dict[str, Any]]:
    """Create BLOCKS and DEPENDS_ON relationships."""
    relationships = []
    
    # Create a few blocking relationships (~5% of issues)
    blocked_issues = [i for i in issues if i['status'] == 'Blocked']
    potential_blockers = [i for i in issues if i['status'] in ['In Progress', 'To Do']]
    
    for blocked in blocked_issues:
        if potential_blockers:
            blocker = random.choice(potential_blockers)
            # BLOCKS: blocker blocks the blocked issue
            relationships.append({
                "type": "BLOCKS",
                "from_id": blocker['id'],
                "to_id": blocked['id'],
                "from_type": "Issue",
                "to_type": "Issue"
            })
            # DEPENDS_ON: blocked issue depends on blocker
            relationships.append({
                "type": "DEPENDS_ON",
                "from_id": blocked['id'],
                "to_id": blocker['id'],
                "from_type": "Issue",
                "to_type": "Issue"
            })
    
    return relationships

def create_bug_story_relationships(bugs: List[Dict]) -> List[Dict[str, Any]]:
    """Create RELATES_TO relationships for bugs linked to stories (undirected)."""
    relationships = []
    
    for bug in bugs:
        if 'related_story_id' in bug:
            relationships.append({
                "type": "RELATES_TO",
                "from_id": bug['id'],
                "to_id": bug['related_story_id'],
                "from_type": "Bug",
                "to_type": "Story"
            })
    
    return relationships

def create_part_of_relationships(issues: List[Dict]) -> List[Dict[str, Any]]:
    """Create PART_OF relationships: Issue → Epic."""
    relationships = []
    
    for issue in issues:
        relationships.append({
            "type": "PART_OF",
            "from_id": issue['id'],
            "to_id": issue['epic_id'],
            "from_type": "Issue",
            "to_type": "Epic"
        })
    
    return relationships

def create_assigned_to_relationships(issues: List[Dict]) -> List[Dict[str, Any]]:
    """Create ASSIGNED_TO relationships: Issue ↔ Person (undirected)."""
    relationships = []
    
    for issue in issues:
        relationships.append({
            "type": "ASSIGNED_TO",
            "from_id": issue['id'],
            "to_id": issue['assignee_id'],
            "from_type": "Issue",
            "to_type": "Person"
        })
    
    return relationships

def create_reported_by_relationships(issues: List[Dict]) -> List[Dict[str, Any]]:
    """Create REPORTED_BY relationships: Issue → Person."""
    relationships = []
    
    for issue in issues:
        relationships.append({
            "type": "REPORTED_BY",
            "from_id": issue['id'],
            "to_id": issue['reporter_id'],
            "from_type": "Issue",
            "to_type": "Person"
        })
    
    return relationships

def main():
    """Generate all Layer 4 data."""
    print("Generating Layer 4: Jira Stories & Bugs")
    print("=" * 60)
    
    # Load previous layers
    print("\n1. Loading Layers 1-3 data...")
    people, teams, initiatives, epics = load_previous_layers()
    
    # Load Layer 1 relationships for team membership
    with open("../data/layer1_people_teams.json", 'r', encoding='utf-8') as f:
        layer1_data = json.load(f)
    layer1_relationships = layer1_data['relationships']
    
    print(f"   ✓ Loaded {len(people)} people")
    print(f"   ✓ Loaded {len(teams)} teams")
    print(f"   ✓ Loaded {len(initiatives)} initiatives")
    print(f"   ✓ Loaded {len(epics)} epics")
    
    # Generate sprints
    print("\n2. Generating sprints...")
    sprints = generate_sprints()
    print(f"   ✓ Created {len(sprints)} sprints")
    
    # Generate issues
    print("\n3. Generating issues...")
    stories = generate_stories(epics, people, teams, layer1_relationships)
    bugs = generate_bugs(stories, people)
    tasks = generate_tasks(epics, people)
    
    all_issues = stories + bugs + tasks
    print(f"   ✓ Created {len(stories)} stories")
    print(f"   ✓ Created {len(bugs)} bugs")
    print(f"   ✓ Created {len(tasks)} tasks")
    print(f"   Total issues: {len(all_issues)}")
    
    # Generate relationships
    print("\n4. Creating relationships...")
    part_of_rels = create_part_of_relationships(all_issues)
    assigned_to_rels = create_assigned_to_relationships(all_issues)
    reported_by_rels = create_reported_by_relationships(all_issues)
    in_sprint_rels = assign_issues_to_sprints(all_issues, sprints)
    dependency_rels = create_issue_dependencies(all_issues)
    bug_story_rels = create_bug_story_relationships(bugs)
    
    all_relationships = (part_of_rels + assigned_to_rels + reported_by_rels + 
                        in_sprint_rels + dependency_rels + bug_story_rels)
    
    print(f"   ✓ PART_OF: {len(part_of_rels)}")
    print(f"   ✓ ASSIGNED_TO: {len(assigned_to_rels)}")
    print(f"   ✓ REPORTED_BY: {len(reported_by_rels)}")
    print(f"   ✓ IN_SPRINT: {len(in_sprint_rels)}")
    print(f"   ✓ BLOCKS/DEPENDS_ON: {len(dependency_rels)}")
    print(f"   ✓ RELATES_TO: {len(bug_story_rels)}")
    print(f"   Total: {len(all_relationships)} relationships")
    
    # Status distribution summary
    print("\n5. Status distribution:")
    status_counts = {}
    for issue in all_issues:
        status = issue['status']
        status_counts[status] = status_counts.get(status, 0) + 1
    for status, count in sorted(status_counts.items()):
        percentage = (count / len(all_issues)) * 100
        print(f"   {status}: {count} ({percentage:.1f}%)")
    
    # Create output structure
    output = {
        "metadata": {
            "layer": "Layer 4",
            "description": "Jira Stories, Bugs, Tasks & Sprints",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1",
            "depends_on": ["layer1_people_teams.json", "layer2_initiatives.json", "layer3_epics.json"]
        },
        "nodes": {
            "issues": all_issues,
            "sprints": sprints
        },
        "relationships": all_relationships,
        "statistics": {
            "issues": len(all_issues),
            "stories": len(stories),
            "bugs": len(bugs),
            "tasks": len(tasks),
            "sprints": len(sprints),
            "relationships": len(all_relationships)
        }
    }
    
    # Write to file
    output_path = "../data/layer4_stories_bugs.json"
    print(f"\n6. Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print("   ✓ Data written successfully")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total Nodes: {len(all_issues) + len(sprints)}")
    print(f"  - Issues: {len(all_issues)} (Stories: {len(stories)}, Bugs: {len(bugs)}, Tasks: {len(tasks)})")
    print(f"  - Sprints: {len(sprints)}")
    print(f"\nTotal Relationships: {len(all_relationships)}")
    print(f"  - PART_OF: {len(part_of_rels)}")
    print(f"  - ASSIGNED_TO: {len(assigned_to_rels)}")
    print(f"  - REPORTED_BY: {len(reported_by_rels)}")
    print(f"  - IN_SPRINT: {len(in_sprint_rels)}")
    print(f"  - BLOCKS/DEPENDS_ON: {len(dependency_rels)}")
    print(f"  - RELATES_TO: {len(bug_story_rels)}")
    print(f"\nOutput file: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
