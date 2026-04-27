"""
Load Pull Requests into Neo4j.
This loads Layer 8 of the graph: PullRequest nodes with their relationships.

Key differences from previous layers:
- PullRequest nodes have nullable datetimes (merged_at, closed_at)
- REVIEWED_BY relationships have properties (state: APPROVED/CHANGES_REQUESTED/COMMENTED)
- Multiple relationship types connecting PRs to commits, branches, and people
- Follows the same pattern: merge nodes one at a time, caller may/may not have relationships
"""

import json
import os

from neo4j import GraphDatabase
from db.models import PullRequest, Relationship, merge_pull_request, merge_relationship, create_constraints


def load_pull_requests_to_neo4j():
    """Load PullRequest nodes into Neo4j."""
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer8_pull_requests.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Create constraints for Layer 8
            create_constraints(session, layers=[8])
            
            # Load pull requests one at a time
            pull_requests = data['nodes']['pull_requests']
            for pr_data in pull_requests:
                # Create PullRequest object (no relationships embedded)
                pull_request = PullRequest(
                    id=pr_data['id'],
                    number=pr_data['number'],
                    title=pr_data['title'],
                    state=pr_data['state'],
                    created_at=pr_data['created_at'],
                    updated_at=pr_data['updated_at'],
                    merged_at=pr_data.get('merged_at'),  # Nullable
                    closed_at=pr_data.get('closed_at'),  # Nullable
                    commits_count=pr_data['commits_count'],
                    additions=pr_data['additions'],
                    deletions=pr_data['deletions'],
                    changed_files=pr_data['changed_files'],
                    comments=pr_data['comments'],
                    review_comments=pr_data['review_comments'],
                    head_branch_name=pr_data['head_branch_name'],
                    base_branch_name=pr_data['base_branch_name'],
                    labels=pr_data['labels'],
                    mergeable_state=pr_data['mergeable_state']
                )
                
                # Merge pull request (without relationships for now)
                merge_pull_request(session, pull_request)
            
            print(f"✓ Loaded {len(pull_requests)} pull requests")
    
    finally:
        driver.close()


def load_relationships():
    """Load all Layer 8 relationships.
    
    Relationships:
    - INCLUDES: PullRequest → Commit (no properties, only for merged PRs)
    - TARGETS: PullRequest → Branch (no properties, base branch)
    - CREATED_BY: PullRequest → Person (no properties)
    - REVIEWED_BY: PullRequest → Person (with state property)
    - REQUESTED_REVIEWER: PullRequest → Person (no properties)
    - MERGED_BY: PullRequest → Person (no properties, only for merged PRs)
    """
    # Read the data file
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'layer8_pull_requests.json')
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    # Connect to Neo4j
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            # Group relationships by type for reporting
            rel_counts = {}
            
            # Process relationships one at a time
            for rel_data in data['relationships']:
                rel_type = rel_data['type']
                rel_counts[rel_type] = rel_counts.get(rel_type, 0) + 1
                
                # Create Relationship object (with properties if present)
                relationship = Relationship(
                    type=rel_data['type'],
                    from_id=rel_data['from_id'],
                    to_id=rel_data['to_id'],
                    from_type=rel_data['from_type'],
                    to_type=rel_data['to_type'],
                    properties=rel_data.get('properties', {})
                )
                
                # Merge relationship (handles bidirectional automatically)
                merge_relationship(session, relationship)
            
            # Report relationship counts
            print(f"✓ Loaded {len(data['relationships'])} relationships:")
            for rel_type, count in sorted(rel_counts.items()):
                print(f"  - {rel_type}: {count}")
    
    finally:
        driver.close()


def validate_layer8():
    """Run validation queries to verify Layer 8 data."""
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    user = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    try:
        with driver.session() as session:
            print("\n" + "=" * 60)
            print("LAYER 8 VALIDATION")
            print("=" * 60)
            
            # 1. PR counts by state
            print("\n1. Pull Requests by State:")
            result = session.run("""
                MATCH (pr:PullRequest)
                RETURN pr.state, count(pr) as count
                ORDER BY count DESC
            """)
            total = 0
            for record in result:
                count = record['count']
                total += count
                print(f"   {record['pr.state']}: {count}")
            print(f"   Total: {total}")
            
            # 2. PRs by repository (from id prefix)
            print("\n2. Pull Requests by Repository:")
            result = session.run("""
                MATCH (pr:PullRequest)
                WITH pr, split(pr.id, '_')[1] as repo
                RETURN repo, count(pr) as pr_count
                ORDER BY pr_count DESC
            """)
            for record in result:
                print(f"   {record['repo']}: {record['pr_count']} PRs")
            
            # 3. Top PR creators
            print("\n3. Top 10 PR Creators:")
            result = session.run("""
                MATCH (pr:PullRequest)-[:CREATED_BY]->(p:Person)
                RETURN p.name, count(pr) as prs_created
                ORDER BY prs_created DESC
                LIMIT 10
            """)
            for record in result:
                print(f"   {record['p.name']}: {record['prs_created']} PRs")
            
            # 4. Review statistics
            print("\n4. Review Statistics:")
            result = session.run("""
                MATCH (pr:PullRequest)
                OPTIONAL MATCH (pr)-[r:REVIEWED_BY]->(reviewer:Person)
                WITH pr, count(DISTINCT reviewer) as reviewer_count,
                     collect(DISTINCT r.state) as review_states
                RETURN 
                    count(pr) as total_prs,
                    avg(reviewer_count) as avg_reviewers_per_pr,
                    sum(CASE WHEN reviewer_count > 0 THEN 1 ELSE 0 END) as prs_with_reviews,
                    sum(CASE WHEN 'APPROVED' IN review_states THEN 1 ELSE 0 END) as prs_with_approvals
            """)
            record = result.single()
            total = record['total_prs']
            with_reviews = record['prs_with_reviews']
            with_approvals = record['prs_with_approvals']
            avg_reviewers = record['avg_reviewers_per_pr']
            print(f"   Total PRs: {total}")
            print(f"   PRs with reviews: {with_reviews} ({with_reviews/total*100:.1f}%)")
            print(f"   PRs with approvals: {with_approvals} ({with_approvals/total*100:.1f}%)")
            print(f"   Avg reviewers per PR: {avg_reviewers:.1f}")
            
            # 5. Review states distribution
            print("\n5. Review States Distribution:")
            result = session.run("""
                MATCH (pr:PullRequest)-[r:REVIEWED_BY]->(p:Person)
                RETURN r.state as review_state, count(*) as count
                ORDER BY count DESC
            """)
            for record in result:
                print(f"   {record['review_state']}: {record['count']}")
            
            # 6. Merged PRs statistics
            print("\n6. Merged PRs Statistics:")
            result = session.run("""
                MATCH (pr:PullRequest {state: 'merged'})
                OPTIONAL MATCH (pr)-[:INCLUDES]->(c:Commit)
                OPTIONAL MATCH (pr)-[:MERGED_BY]->(merger:Person)
                WITH pr, count(DISTINCT c) as commit_count, merger
                RETURN 
                    count(pr) as merged_prs,
                    avg(commit_count) as avg_commits_per_pr,
                    sum(CASE WHEN merger IS NOT NULL THEN 1 ELSE 0 END) as with_merger
            """)
            record = result.single()
            merged = record['merged_prs']
            avg_commits = record['avg_commits_per_pr']
            with_merger = record['with_merger']
            print(f"   Merged PRs: {merged}")
            print(f"   Avg commits per merged PR: {avg_commits:.1f}")
            print(f"   PRs with MERGED_BY: {with_merger}")
            
            # 7. PR size distribution
            print("\n7. PR Size Distribution:")
            result = session.run("""
                MATCH (pr:PullRequest)
                WITH pr,
                     CASE 
                         WHEN pr.commits_count <= 3 THEN 'Small (1-3 commits)'
                         WHEN pr.commits_count <= 8 THEN 'Medium (4-8 commits)'
                         ELSE 'Large (9+ commits)'
                     END as size_category
                RETURN size_category, count(pr) as count
                ORDER BY 
                    CASE size_category
                        WHEN 'Small (1-3 commits)' THEN 1
                        WHEN 'Medium (4-8 commits)' THEN 2
                        ELSE 3
                    END
            """)
            for record in result:
                print(f"   {record['size_category']}: {record['count']}")
            
            # 8. Verify bidirectional relationships
            print("\n8. Bidirectional Relationship Verification:")
            
            # Check INCLUDES
            result = session.run("""
                MATCH (pr:PullRequest)-[:INCLUDES]->(c:Commit)
                WHERE NOT exists((c)-[:INCLUDED_IN]->(pr))
                RETURN count(*) as missing
            """)
            count = result.single()['missing']
            if count == 0:
                print("   ✓ INCLUDES ↔ INCLUDED_IN: All bidirectional")
            else:
                print(f"   ✗ INCLUDES ↔ INCLUDED_IN: {count} missing reverse")
            
            # Check REVIEWED_BY (with property matching)
            result = session.run("""
                MATCH (pr:PullRequest)-[r1:REVIEWED_BY]->(p:Person)
                MATCH (p)-[r2:REVIEWED]->(pr)
                WHERE r1.state <> r2.state
                RETURN count(*) as mismatched
            """)
            count = result.single()['mismatched']
            if count == 0:
                print("   ✓ REVIEWED_BY ↔ REVIEWED: All properties match")
            else:
                print(f"   ✗ REVIEWED_BY ↔ REVIEWED: {count} property mismatches")
            
            print("\n" + "=" * 60)
    
    finally:
        driver.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Loading Layer 8: Pull Requests")
    print("=" * 60)
    
    load_pull_requests_to_neo4j()
    load_relationships()
    validate_layer8()
    
    print("\n✓ Layer 8 loading complete!")
