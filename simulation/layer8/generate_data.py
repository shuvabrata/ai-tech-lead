"""
Layer 8: Pull Requests Data Generation
Generates realistic PR data with reviews, approvals, and commit linkage.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
LAYER = "Layer 8"
DESCRIPTION = "Pull Requests"
VERSION = "0.1"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "layer8_pull_requests.json"

# Load dependencies
DATA_DIR = Path(__file__).parent.parent / "data"
LAYER1_FILE = DATA_DIR / "layer1_people_teams.json"
LAYER6_FILE = DATA_DIR / "layer6_branches.json"
LAYER7_FILE = DATA_DIR / "layer7_commits.json"

# PR Distribution (from design doc)
TOTAL_PRS = 100
PR_STATES = {
    "merged": 0.75,    # 75 PRs
    "open": 0.15,      # 15 PRs
    "closed": 0.10     # 10 PRs (closed without merge)
}

PR_SIZES = {
    "small": (1, 3, 0.40),    # 1-3 commits, 40%
    "medium": (4, 8, 0.40),   # 4-8 commits, 40%
    "large": (9, 20, 0.20)    # 9-20 commits, 20%
}

# Repository PR distribution (matches actual repo names from Layer 5)
REPO_PR_DISTRIBUTION = {
    "k8s-infrastructure": 20,
    "service-mesh": 5,
    "gateway": 10,
    "user-service": 10,
    "order-service": 10,
    "web-app": 25,
    "ios-app": 15,
    "streaming-pipeline": 5
}

PR_LABELS = [
    ["feature"],
    ["bugfix"],
    ["feature", "enhancement"],
    ["bugfix", "urgent"],
    ["documentation"],
    ["refactor"],
    ["performance"],
    ["security"],
    []  # no labels
]

MERGEABLE_STATES = ["clean", "dirty", "blocked", "unknown"]

def load_json(filepath):
    """Load JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_random_pr_size():
    """Get random PR size category."""
    rand = random.random()
    cumulative = 0
    for size, (min_commits, max_commits, prob) in PR_SIZES.items():
        cumulative += prob
        if rand <= cumulative:
            return size, random.randint(min_commits, max_commits)
    return "medium", random.randint(4, 8)

def get_pr_state():
    """Get random PR state based on distribution."""
    rand = random.random()
    cumulative = 0
    for state, prob in PR_STATES.items():
        cumulative += prob
        if rand <= cumulative:
            return state
    return "merged"

def generate_pr_title(repo_name, commit_messages):
    """Generate PR title based on commits."""
    templates = [
        "feat: {feature}",
        "fix: {fix}",
        "refactor: {refactor}",
        "docs: {docs}",
        "perf: {perf}",
        "test: {test}",
    ]
    
    # Extract action from commits
    if any("Fix" in msg or "fix" in msg for msg in commit_messages):
        return f"fix: Resolve issues in {repo_name.split('/')[-1]}"
    elif any("Add" in msg or "Implement" in msg for msg in commit_messages):
        return f"feat: Add new functionality to {repo_name.split('/')[-1]}"
    elif any("Update" in msg for msg in commit_messages):
        return f"chore: Update {repo_name.split('/')[-1]} components"
    elif any("Refactor" in msg for msg in commit_messages):
        return f"refactor: Improve {repo_name.split('/')[-1]} code structure"
    else:
        return f"feat: Enhance {repo_name.split('/')[-1]}"

def generate_pr_description(title, commits_count):
    """Generate PR description."""
    descriptions = [
        f"This PR introduces improvements to the codebase.\n\n## Changes\n- Includes {commits_count} commits\n- Addresses technical requirements\n\n## Testing\n- Unit tests added\n- Manual testing completed",
        f"## Summary\nThis pull request implements requested features.\n\n## Details\n- {commits_count} commits included\n- Code reviewed and tested\n\n## Impact\n- Minimal risk\n- Ready for merge",
        f"## Overview\n{title}\n\n## Commits\n{commits_count} commits in this PR\n\n## Checklist\n- [x] Tests passing\n- [x] Documentation updated\n- [x] Code reviewed",
    ]
    return random.choice(descriptions)

def main():
    print(f"=== {LAYER}: {DESCRIPTION} ===\n")
    
    # Load dependencies
    print("Loading dependencies...")
    layer1_data = load_json(LAYER1_FILE)
    layer6_data = load_json(LAYER6_FILE)
    layer7_data = load_json(LAYER7_FILE)
    
    people = layer1_data["nodes"]["people"]
    branches = layer6_data["nodes"]["branches"]
    commits = layer7_data["nodes"]["commits"]
    
    # Filter engineers (exclude managers for PR authors)
    engineers = [p for p in people if p["role"] == "Engineer"]
    
    # Get default branches by repository
    default_branches_by_repo = {}
    repo_branches = {}
    
    for branch in branches:
        # Extract repo name from branch id
        branch_id = branch["id"]
        if branch["is_default"]:
            # Format: branch_main_repo_k8s_infrastructure
            repo_part = branch_id.replace("branch_main_repo_", "").replace("branch_main_", "")
            default_branches_by_repo[repo_part] = branch["id"]
        
        # Group all branches by repo for FROM relationship
        repo_key = branch_id.split("_repo_")[-1].split("_")[0] if "_repo_" in branch_id else None
        if repo_key:
            if repo_key not in repo_branches:
                repo_branches[repo_key] = []
            repo_branches[repo_key].append(branch)
    
    # Group commits by branch (for INCLUDES relationship)
    commits_by_branch = {}
    for rel in layer7_data["relationships"]:
        if rel["type"] == "PART_OF" and rel["to_type"] == "Branch":
            branch_id = rel["to_id"]
            commit_id = rel["from_id"]
            if branch_id not in commits_by_branch:
                commits_by_branch[branch_id] = []
            commits_by_branch[branch_id].append(commit_id)
    
    # Sort commits by timestamp for sequential PR assignment
    def get_commit_datetime(commit):
        """Return commit datetime from current or legacy commit date fields."""
        commit_time = commit.get("created_at") or commit.get("timestamp")
        if not commit_time:
            # Keep generation resilient if upstream commit data is incomplete.
            return datetime.now()
        return datetime.fromisoformat(commit_time)

    commit_timestamps = {}
    for commit in commits:
        commit_timestamps[commit["id"]] = get_commit_datetime(commit)
    
    print(f"  - Loaded {len(people)} people")
    print(f"  - Loaded {len(branches)} branches")
    print(f"  - Loaded {len(commits)} commits")
    print(f"  - Found {len(default_branches_by_repo)} repositories with default branches")
    print()
    
    # Generate PRs
    print(f"Generating {TOTAL_PRS} pull requests...")
    
    pull_requests = []
    relationships = []
    pr_counter = 1
    
    # Track used commits to avoid duplicates
    used_commits = set()
    
    # Distribute PRs across repositories
    for repo_name, pr_count in REPO_PR_DISTRIBUTION.items():
        repo_key = repo_name.replace("-", "_")
        
        # Find default branch for this repo
        default_branch_id = None
        for key, branch_id in default_branches_by_repo.items():
            if repo_key in key or repo_name.replace("-", "_") in key:
                default_branch_id = branch_id
                break
        
        if not default_branch_id:
            print(f"  Warning: No default branch found for {repo_name}, skipping...")
            continue
        
        # Get available commits for this repo
        available_commits = commits_by_branch.get(default_branch_id, [])
        if not available_commits:
            print(f"  Warning: No commits found for {repo_name}, skipping...")
            continue
        
        # Sort commits chronologically
        available_commits.sort(key=lambda c: commit_timestamps.get(c, datetime.now()))
        
        print(f"  {repo_name}: Generating {pr_count} PRs from {len(available_commits)} commits")
        
        for i in range(pr_count):
            if pr_counter > TOTAL_PRS:
                break
            
            # Determine PR state
            pr_state = get_pr_state()
            
            # Determine PR size
            size_category, commits_count = get_random_pr_size()
            
            # Select commits for this PR (only for merged PRs)
            pr_commit_ids = []
            if pr_state == "merged":
                # Select sequential commits that haven't been used
                remaining_commits = [c for c in available_commits if c not in used_commits]
                if len(remaining_commits) >= commits_count:
                    pr_commit_ids = remaining_commits[:commits_count]
                    used_commits.update(pr_commit_ids)
                elif remaining_commits:
                    # Use what's available
                    pr_commit_ids = remaining_commits
                    used_commits.update(pr_commit_ids)
                    commits_count = len(pr_commit_ids)
            
            # Get commit details for merged PRs
            commit_messages = []
            total_additions = 0
            total_deletions = 0
            changed_files = 0
            
            if pr_state == "merged" and pr_commit_ids:
                for commit_id in pr_commit_ids:
                    commit_data = next((c for c in commits if c["id"] == commit_id), None)
                    if commit_data:
                        commit_messages.append(commit_data["message"])
                        total_additions += commit_data["additions"]
                        total_deletions += commit_data["deletions"]
                        changed_files += commit_data["files_changed"]
            else:
                # For open/closed PRs, generate synthetic metrics
                total_additions = random.randint(10, 500)
                total_deletions = random.randint(5, 200)
                changed_files = random.randint(1, 15)
            
            # Generate PR data
            pr_id = f"pr_{repo_key}_{pr_counter}"
            pr_number = pr_counter
            
            # Generate title
            if commit_messages:
                pr_title = generate_pr_title(repo_name, commit_messages)
            else:
                pr_title = generate_pr_title(repo_name, [f"Feature for {repo_name}"])
            
            # Generate description
            pr_description = generate_pr_description(pr_title, commits_count)
            
            # Generate timestamps
            if pr_state == "merged" and pr_commit_ids:
                # Use first commit timestamp as base
                first_commit = next((c for c in commits if c["id"] == pr_commit_ids[0]), None)
                if first_commit:
                    base_time = get_commit_datetime(first_commit)
                else:
                    base_time = datetime.now() - timedelta(days=random.randint(30, 90))
            else:
                base_time = datetime.now() - timedelta(days=random.randint(1, 30))
            
            created_at = base_time - timedelta(hours=random.randint(24, 72))
            updated_at = base_time + timedelta(hours=random.randint(1, 48))
            
            merged_at = None
            closed_at = None
            
            if pr_state == "merged":
                merged_at = base_time + timedelta(hours=random.randint(24, 120))
                closed_at = merged_at
            elif pr_state == "closed":
                closed_at = created_at + timedelta(hours=random.randint(12, 72))
            
            # Select author (engineer)
            author = random.choice(engineers)
            
            # Determine labels
            labels = random.choice(PR_LABELS)
            
            # Determine mergeable state
            if pr_state == "open":
                mergeable_state = random.choice(MERGEABLE_STATES)
            else:
                mergeable_state = "clean"
            
            # Generate source branch name
            jira_key = random.choice(["PLAT", "PORT", "DATA", ""])
            if jira_key:
                jira_num = random.randint(1, 120)
                head_branch_name = f"feature/{jira_key}-{jira_num}-implement-feature"
            else:
                head_branch_name = f"feature/update-{repo_name.split('/')[-1]}"
            
            # Create PR node
            pr_node = {
                "id": pr_id,
                "number": pr_number,
                "title": pr_title,
                "description": pr_description,
                "state": pr_state,
                "created_at": created_at.isoformat(),
                "updated_at": updated_at.isoformat(),
                "merged_at": merged_at.isoformat() if merged_at else None,
                "closed_at": closed_at.isoformat() if closed_at else None,
                "draft": random.random() < 0.1,  # 10% are drafts
                "commits_count": commits_count,
                "additions": total_additions,
                "deletions": total_deletions,
                "changed_files": changed_files,
                "comments": random.randint(0, 15),
                "review_comments": random.randint(0, 25),
                "head_branch_name": head_branch_name,
                "base_branch_name": "main",
                "labels": labels,
                "mergeable_state": mergeable_state
            }
            
            pull_requests.append(pr_node)
            
            # Create relationships
            
            # TARGETS relationship (always to main/default branch)
            relationships.append({
                "type": "TARGETS",
                "from_id": pr_id,
                "to_id": default_branch_id,
                "from_type": "PullRequest",
                "to_type": "Branch"
            })
            
            # FROM relationship (to source branch if it exists and not deleted)
            # For simplicity, we'll skip this in simulation as most feature branches are deleted
            
            # CREATED_BY relationship
            relationships.append({
                "type": "CREATED_BY",
                "from_id": pr_id,
                "to_id": author["id"],
                "from_type": "PullRequest",
                "to_type": "Person"
            })
            
            # INCLUDES relationships (only for merged PRs)
            if pr_state == "merged" and pr_commit_ids:
                for commit_id in pr_commit_ids:
                    relationships.append({
                        "type": "INCLUDES",
                        "from_id": pr_id,
                        "to_id": commit_id,
                        "from_type": "PullRequest",
                        "to_type": "Commit"
                    })
            
            # REVIEWED_BY relationships (90% of PRs have at least 1 reviewer)
            if random.random() < 0.9:
                # Select reviewers (different from author)
                potential_reviewers = [p for p in engineers if p["id"] != author["id"]]
                num_reviewers = 1 if random.random() < 0.4 else 2  # 60% have 2+ reviewers
                reviewers = random.sample(potential_reviewers, min(num_reviewers, len(potential_reviewers)))
                
                for reviewer in reviewers:
                    review_state = random.choice([
                        "APPROVED",
                        "APPROVED",
                        "APPROVED",
                        "APPROVED",  # 80% approval rate
                        "CHANGES_REQUESTED",
                        "COMMENTED"
                    ])
                    
                    submitted_at = created_at + timedelta(hours=random.randint(6, 72))
                    
                    relationships.append({
                        "type": "REVIEWED_BY",
                        "from_id": pr_id,
                        "to_id": reviewer["id"],
                        "from_type": "PullRequest",
                        "to_type": "Person",
                        "properties": {
                            "submitted_at": submitted_at.isoformat(),
                            "state": review_state
                        }
                    })
            
            # REQUESTED_REVIEWER relationships
            # Add 1-3 review requests per PR
            potential_reviewers = [p for p in engineers if p["id"] != author["id"]]
            num_requested = random.randint(1, 3)
            requested_reviewers = random.sample(potential_reviewers, min(num_requested, len(potential_reviewers)))
            
            for requested in requested_reviewers:
                relationships.append({
                    "type": "REQUESTED_REVIEWER",
                    "from_id": pr_id,
                    "to_id": requested["id"],
                    "from_type": "PullRequest",
                    "to_type": "Person"
                })
            
            # MERGED_BY relationship (only for merged PRs)
            if pr_state == "merged":
                # Usually reviewed and merged by senior engineers or the author
                if random.random() < 0.7:
                    merger = random.choice([p for p in engineers if p["seniority"] in ["Senior", "Staff"]])
                else:
                    merger = author
                
                relationships.append({
                    "type": "MERGED_BY",
                    "from_id": pr_id,
                    "to_id": merger["id"],
                    "from_type": "PullRequest",
                    "to_type": "Person"
                })
            
            pr_counter += 1
    
    # Create output
    output_data = {
        "metadata": {
            "layer": LAYER,
            "description": DESCRIPTION,
            "generated_at": datetime.now().isoformat(),
            "version": VERSION,
            "depends_on": [
                "layer1_people_teams.json",
                "layer6_branches.json",
                "layer7_commits.json"
            ]
        },
        "nodes": {
            "pull_requests": pull_requests
        },
        "relationships": relationships
    }
    
    # Save to file
    print(f"\nSaving to {OUTPUT_FILE}...")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    
    # Summary
    print("\n=== Summary ===")
    print(f"Pull Requests created: {len(pull_requests)}")
    
    # Count by state
    state_counts = {}
    for pr in pull_requests:
        state = pr["state"]
        state_counts[state] = state_counts.get(state, 0) + 1
    
    for state, count in sorted(state_counts.items()):
        print(f"  - {state}: {count}")
    
    print(f"\nRelationships created: {len(relationships)}")
    
    # Count by type
    rel_counts = {}
    for rel in relationships:
        rel_type = rel["type"]
        rel_counts[rel_type] = rel_counts.get(rel_type, 0) + 1
    
    for rel_type, count in sorted(rel_counts.items()):
        print(f"  - {rel_type}: {count}")
    
    print("\n✅ Layer 8 data generated successfully!")
    print(f"📁 Output: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
