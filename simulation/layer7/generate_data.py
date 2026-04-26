"""
Layer 7: Git Commits & Files Data Generation

Generates realistic commit history for default branches only.
- ~500 commits over 3 months
- ~300 files
- Links to people, branches, and issues
"""

import json
import random
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

# Constants
TOTAL_COMMITS = 500
START_DATE = datetime(2025, 10, 11)
END_DATE = datetime(2026, 1, 10)

def load_dependencies():
    """Load data from layers 1, 4, 5, 6"""
    data_dir = Path(__file__).parent.parent / "data"
    
    with open(data_dir / "layer1_people_teams.json", encoding="utf-8") as f:
        layer1 = json.load(f)
    with open(data_dir / "layer4_stories_bugs.json", encoding="utf-8") as f:
        layer4 = json.load(f)
    with open(data_dir / "layer5_repositories.json", encoding='utf-8') as f:
        layer5 = json.load(f)
    with open(data_dir / "layer6_branches.json", encoding='utf-8') as f:
        layer6 = json.load(f)
    
    return layer1, layer4, layer5, layer6


def get_default_branches_with_repos(layer5, layer6):
    """Get default branches mapped to their repositories"""
    result = []
    
    # Get all default branches
    default_branches = [b for b in layer6["nodes"]["branches"] if b["is_default"]]
    
    # For each default branch, find its repository
    for branch in default_branches:
        branch_rel = next((r for r in layer6["relationships"] 
                          if r["type"] == "BRANCH_OF" and r["from_id"] == branch["id"]), None)
        if branch_rel:
            repo = next((r for r in layer5["nodes"]["repositories"] 
                        if r["id"] == branch_rel["to_id"]), None)
            if repo:
                result.append({"branch": branch, "repo": repo})
    
    return result


def get_all_engineers(layer1):
    """Get all engineers (not managers) from layer 1"""
    return [p for p in layer1["nodes"]["people"] if p["role"] == "Engineer"]


def generate_commit_sha():
    """Generate realistic commit SHA"""
    return hashlib.sha1(str(random.random()).encode()).hexdigest()[:40]


def generate_timestamp_weighted():
    """Generate timestamp weighted by sprints"""
    sprints = [
        ("2025-12-09", "2025-12-20", 100),  # Sprint 1
        ("2025-12-23", "2026-01-03", 80),   # Sprint 2 (holidays)
        ("2026-01-06", "2026-01-17", 130),  # Sprint 3
        ("2025-10-11", "2025-12-08", 190),  # Pre-sprint period
    ]
    
    # Pick a sprint based on weights
    sprint = random.choices(sprints, weights=[s[2] for s in sprints])[0]
    start = datetime.fromisoformat(sprint[0])
    end = datetime.fromisoformat(sprint[1])
    
    # Random time within sprint
    delta = (end - start).total_seconds()
    random_seconds = random.uniform(0, delta)
    timestamp = start + timedelta(seconds=random_seconds)
    
    # Bias towards working hours on weekdays
    if timestamp.weekday() < 5:  # Weekday
        if timestamp.hour < 9 or timestamp.hour > 18:
            timestamp = timestamp.replace(hour=random.randint(9, 17))
    
    return timestamp


def generate_file_path(repo_name, repo_language):
    """Generate realistic file path for repository"""
    paths_by_lang = {
        "YAML": [
            f"deployments/{random.choice(['auth', 'user', 'order'])}-deployment.yaml",
            f"configs/{random.choice(['dev', 'prod', 'staging'])}-config.yaml",
            "README.md",
            f"scripts/deploy-{random.choice(['dev', 'prod'])}.sh"
        ],
        "Go": [
            f"pkg/{random.choice(['mesh', 'proxy', 'config'])}/handler.go",
            f"internal/service/{random.choice(['auth', 'routing', 'telemetry'])}.go",
            f"cmd/{repo_name}/main.go",
            f"tests/{random.choice(['handler', 'service', 'config'])}_test.go",
            "README.md"
        ],
        "Python": [
            f"src/{random.choice(['api', 'models', 'services'])}/{random.choice(['user', 'auth', 'payment'])}.py",
            f"src/{random.choice(['utils', 'middleware', 'validators'])}/{random.choice(['logger', 'validator', 'parser'])}.py",
            f"tests/test_{random.choice(['api', 'service', 'model'])}.py",
            "requirements.txt",
            "README.md",
            "config.yaml"
        ],
        "TypeScript": [
            f"src/components/{random.choice(['Auth', 'Dashboard', 'Profile', 'Settings'])}.tsx",
            f"src/pages/{random.choice(['Home', 'Login', 'Dashboard'])}.tsx",
            f"src/services/{random.choice(['auth', 'api', 'user'])}Service.ts",
            f"src/hooks/use{random.choice(['Auth', 'Data', 'API'])}.ts",
            f"src/styles/{random.choice(['global', 'theme', 'components'])}.css",
            f"src/__tests__/{random.choice(['Auth', 'Dashboard'])}.test.tsx",
            "package.json",
            "README.md"
        ],
        "Swift": [
            f"Sources/Views/{random.choice(['Login', 'Dashboard', 'Profile'])}View.swift",
            f"Sources/ViewModels/{random.choice(['Login', 'Dashboard', 'Profile'])}ViewModel.swift",
            f"Sources/Models/{random.choice(['User', 'Order', 'Product'])}.swift",
            f"Sources/Services/{random.choice(['Auth', 'API', 'Storage'])}Service.swift",
            f"Tests/{random.choice(['Login', 'Dashboard', 'Profile'])}Tests.swift",
            "README.md"
        ]
    }
    
    templates = paths_by_lang.get(repo_language, [
        f"src/main.{repo_language.lower()}",
        f"src/utils.{repo_language.lower()}",
        "README.md"
    ])
    
    return random.choice(templates)


def generate_files_for_all_repos(branch_repo_pairs):
    """Generate file nodes for all repositories"""
    all_files = []
    file_counter = 0
    
    for pair in branch_repo_pairs:
        repo = pair["repo"]
        repo_name = repo["name"]
        repo_lang = repo["language"]
        
        # Generate 30-40 files per repo
        num_files = random.randint(30, 40)
        generated_paths = set()
        
        for _ in range(num_files):
            # Generate unique path for this repo
            path = generate_file_path(repo_name, repo_lang)
            # Ensure uniqueness
            counter = 0
            while path in generated_paths and counter < 10:
                path = generate_file_path(repo_name, repo_lang)
                counter += 1
            generated_paths.add(path)
            
            name = Path(path).name
            extension = Path(path).suffix or ".txt"
            
            # Determine language from extension
            ext_to_lang = {
                ".py": "Python", ".go": "Go", ".yaml": "YAML", ".yml": "YAML",
                ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
                ".swift": "Swift", ".java": "Java",
                ".md": "Markdown", ".json": "JSON", ".sh": "Shell", ".css": "CSS"
            }
            file_lang = ext_to_lang.get(extension, repo_lang)
            
            # Determine if test file
            is_test = any(x in path.lower() for x in ["test", "spec", "__tests__", "tests/"])
            
            # Create file node
            file_id = f"file_{repo['id']}_{file_counter}"
            all_files.append({
                "id": file_id,
                "path": path,
                "name": name,
                "extension": extension,
                "language": file_lang,
                "is_test": is_test,
                "size": random.randint(100, 50000),
                "created_at": (START_DATE + timedelta(days=random.randint(0, 30))).isoformat(),
                "repo_id": repo["id"]  # temporary for commit generation
            })
            file_counter += 1
    
    return all_files


def generate_commit_message(issue_keys):
    """Generate realistic commit message"""
    # 80% have Jira reference, 20% don't
    has_jira = random.random() < 0.8
    
    if has_jira and issue_keys:
        # 75% stories, 25% bugs
        issue_type = random.choice(["Story"] * 3 + ["Bug"])
        matching_keys = [k for k, t in issue_keys.items() if t == issue_type]
        
        if matching_keys:
            key = random.choice(matching_keys)
            if issue_type == "Story":
                templates = [
                    f"[{key}] Add {{feature}} to {{component}}",
                    f"[{key}] Implement {{feature}} for {{component}}",
                    f"[{key}] Build {{feature}} component"
                ]
                message = random.choice(templates).format(
                    feature=random.choice(["authentication", "API endpoints", "validation", "caching"]),
                    component=random.choice(["service", "controller", "handler", "middleware"])
                )
            else:
                templates = [
                    f"Fix {{bug}} in {{component}} ({key})",
                    f"[{key}] Resolve {{bug}} issue",
                    f"Fix memory leak in {{component}} ({key})"
                ]
                message = random.choice(templates).format(
                    bug=random.choice(["null pointer", "memory leak", "race condition", "timeout"]),
                    component=random.choice(["service", "handler", "processor", "validator"])
                )
            return message, key
    
    # No Jira reference
    templates = [
        "Update README",
        "Refactor {component} for better performance",
        "Clean up {component} code",
        "Add documentation for {component}"
    ]
    message = random.choice(templates)
    if "{component}" in message:
        message = message.format(component=random.choice(["service", "API", "config", "tests"]))
    
    return message, None


def generate_commits(engineers, branch_repo_pairs, all_files, issues):
    """Generate commit nodes"""
    commits = []
    
    # Build issue key lookup
    issue_keys = {issue["key"]: issue["type"] for issue in issues}
    
    # Build files by repo
    files_by_repo = {}
    for file in all_files:
        repo_id = file["repo_id"]
        if repo_id not in files_by_repo:
            files_by_repo[repo_id] = []
        files_by_repo[repo_id].append(file)
    
    # Weight engineers by seniority
    weighted_engineers = []
    for eng in engineers:
        weight = {"Junior": 1, "Mid": 3, "Senior": 5, "Staff": 7}.get(eng.get("seniority", "Mid"), 3)
        weighted_engineers.extend([eng] * weight)
    
    # Generate commits
    for i in range(TOTAL_COMMITS):
        # Pick random branch/repo pair
        pair = random.choice(branch_repo_pairs)
        branch = pair["branch"]
        repo = pair["repo"]
        
        # Pick random author
        author = random.choice(weighted_engineers)
        
        # Generate timestamp
        timestamp = generate_timestamp_weighted()
        
        # Pick files to modify (1-5 files)
        repo_files = files_by_repo.get(repo["id"], [])
        if not repo_files:
            continue
        
        num_files = random.choices([1, 2, 3, 4, 5], weights=[30, 40, 20, 7, 3])[0]
        modified_files = random.sample(repo_files, min(num_files, len(repo_files)))
        
        # Generate stats
        additions = random.randint(1, 500)
        deletions = random.randint(0, additions // 2)
        
        # Generate message
        message, issue_key = generate_commit_message(issue_keys)
        
        # Create commit
        commit_id = f"commit_{i}"
        commits.append({
            "id": commit_id,
            "sha": generate_commit_sha(),
            "message": message,
            "created_at": timestamp.isoformat(),
            "additions": additions,
            "deletions": deletions,
            "files_changed": len(modified_files),
            # Temp fields for relationship building
            "author_id": author["id"],
            "branch_id": branch["id"],
            "modified_files": modified_files,
            "issue_key": issue_key
        })
    
    # Sort by created_at
    commits.sort(key=lambda c: c["created_at"])
    
    return commits


def build_relationships(commits, issues):
    """Build all relationships"""
    relationships = []
    
    # Build issue lookup
    issue_lookup = {i["key"]: i["id"] for i in issues}
    
    for commit in commits:
        # PART_OF: Commit → Branch
        relationships.append({
            "type": "PART_OF",
            "from_id": commit["id"],
            "to_id": commit["branch_id"],
            "from_type": "Commit",
            "to_type": "Branch"
        })
        
        # AUTHORED_BY: Commit ↔ Person (undirected)
        relationships.append({
            "type": "AUTHORED_BY",
            "from_id": commit["id"],
            "to_id": commit["author_id"],
            "from_type": "Commit",
            "to_type": "Person"
        })
        
        # MODIFIES: Commit → File (with per-file stats)
        for file in commit["modified_files"]:
            # Generate per-file stats
            file_additions = random.randint(1, max(1, commit["additions"] // len(commit["modified_files"])))
            file_deletions = random.randint(0, max(1, commit["deletions"] // len(commit["modified_files"])))
            
            relationships.append({
                "type": "MODIFIES",
                "from_id": commit["id"],
                "to_id": file["id"],
                "from_type": "Commit",
                "to_type": "File",
                "properties": {
                    "additions": file_additions,
                    "deletions": file_deletions
                }
            })
        
        # REFERENCES: Commit → Issue
        if commit["issue_key"] and commit["issue_key"] in issue_lookup:
            relationships.append({
                "type": "REFERENCES",
                "from_id": commit["id"],
                "to_id": issue_lookup[commit["issue_key"]],
                "from_type": "Commit",
                "to_type": "Issue"
            })
    
    return relationships


def main():
    print("🚀 Generating Layer 7: Git Commits & Files\n")
    
    # Load dependencies
    print("📖 Loading dependencies...")
    layer1, layer4, layer5, layer6 = load_dependencies()
    
    engineers = get_all_engineers(layer1)
    branch_repo_pairs = get_default_branches_with_repos(layer5, layer6)
    issues = layer4["nodes"]["issues"]
    
    print(f"   ✓ {len(engineers)} engineers")
    print(f"   ✓ {len(branch_repo_pairs)} repositories with default branches")
    print(f"   ✓ {len(issues)} issues\n")
    
    # Generate files
    print("📁 Generating files...")
    all_files = generate_files_for_all_repos(branch_repo_pairs)
    print(f"   ✓ Generated {len(all_files)} files\n")
    
    # Generate commits
    print("💾 Generating commits...")
    commits = generate_commits(engineers, branch_repo_pairs, all_files, issues)
    print(f"   ✓ Generated {len(commits)} commits\n")
    
    # Build relationships
    print("🔗 Building relationships...")
    relationships = build_relationships(commits, issues)
    
    part_of = len([r for r in relationships if r["type"] == "PART_OF"])
    authored_by = len([r for r in relationships if r["type"] == "AUTHORED_BY"])
    modifies = len([r for r in relationships if r["type"] == "MODIFIES"])
    references = len([r for r in relationships if r["type"] == "REFERENCES"])
    
    print(f"   ✓ {part_of} PART_OF")
    print(f"   ✓ {authored_by} AUTHORED_BY")
    print(f"   ✓ {modifies} MODIFIES")
    print(f"   ✓ {references} REFERENCES\n")
    
    # Clean up temporary fields
    for commit in commits:
        del commit["author_id"]
        del commit["branch_id"]
        del commit["modified_files"]
        del commit["issue_key"]
    
    for file in all_files:
        del file["repo_id"]
    
    # Build output
    output = {
        "metadata": {
            "layer": "Layer 7",
            "description": "Git Commits & Files",
            "generated_at": datetime.now().isoformat(),
            "version": "0.1",
            "depends_on": [
                "layer1_people_teams.json",
                "layer4_stories_bugs.json",
                "layer5_repositories.json",
                "layer6_branches.json"
            ]
        },
        "nodes": {
            "commits": commits,
            "files": all_files
        },
        "relationships": relationships
    }
    
    # Save
    output_path = Path(__file__).parent.parent / "data" / "layer7_commits.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    print("✅ Layer 7 generated successfully!")
    print(f"   📊 {len(commits)} commits")
    print(f"   📁 {len(all_files)} files")
    print(f"   🔗 {len(relationships)} relationships")
    print(f"   💾 Saved to: {output_path}\n")
    
    # Statistics
    print("📈 Statistics:")
    if commits:
        print(
            f"   • Commits with Jira refs: {references} "
            f"({references / len(commits) * 100:.1f}%)"
        )
        print(
            "   • Avg files per commit: "
            f"{sum(c['files_changed'] for c in commits) / len(commits):.1f}"
        )
        print(
            "   • Avg additions per commit: "
            f"{sum(c['additions'] for c in commits) / len(commits):.0f}"
        )
        print(
            f"   • Date range: {commits[0]['created_at'][:10]} "
            f"to {commits[-1]['created_at'][:10]}"
        )
    else:
        print("   • No commits generated")


if __name__ == "__main__":
    main()
