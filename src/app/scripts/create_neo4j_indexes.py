#!/usr/bin/env python3
"""
Create all recommended indexes for the project graph database.
Run this after loading all data layers.
"""

import os
import sys
from neo4j import GraphDatabase

NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USERNAME', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'password123')


def create_indexes():
    """Create all recommended indexes."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    # Priority 1: High-Impact Lookup Indexes
    priority1 = [
        "CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.name)",
        # person_email index removed - covered by UNIQUE constraint in create_constraints()
        "CREATE INDEX person_role IF NOT EXISTS FOR (p:Person) ON (p.role)",
        "CREATE INDEX person_title IF NOT EXISTS FOR (p:Person) ON (p.title)",
        "CREATE INDEX person_seniority IF NOT EXISTS FOR (p:Person) ON (p.seniority)",
        "CREATE INDEX team_name IF NOT EXISTS FOR (t:Team) ON (t.name)",
        "CREATE INDEX identity_username IF NOT EXISTS FOR (i:IdentityMapping) ON (i.username)",
        "CREATE INDEX identity_provider IF NOT EXISTS FOR (i:IdentityMapping) ON (i.provider)",
        "CREATE INDEX identity_email IF NOT EXISTS FOR (i:IdentityMapping) ON (i.email)",
        "CREATE INDEX initiative_key IF NOT EXISTS FOR (i:Initiative) ON (i.key)",
        "CREATE INDEX epic_key IF NOT EXISTS FOR (e:Epic) ON (e.key)",
        "CREATE INDEX issue_key IF NOT EXISTS FOR (i:Issue) ON (i.key)",
        "CREATE INDEX repository_name IF NOT EXISTS FOR (r:Repository) ON (r.name)",
        "CREATE INDEX repository_full_name IF NOT EXISTS FOR (r:Repository) ON (r.full_name)",
        "CREATE INDEX repository_language IF NOT EXISTS FOR (r:Repository) ON (r.language)",
        "CREATE INDEX branch_name IF NOT EXISTS FOR (b:Branch) ON (b.name)",
        "CREATE INDEX file_path IF NOT EXISTS FOR (f:File) ON (f.path)",
        "CREATE INDEX file_name IF NOT EXISTS FOR (f:File) ON (f.name)",
        "CREATE INDEX file_extension IF NOT EXISTS FOR (f:File) ON (f.extension)",
        "CREATE INDEX file_language IF NOT EXISTS FOR (f:File) ON (f.language)",
        "CREATE INDEX pr_number IF NOT EXISTS FOR (pr:PullRequest) ON (pr.number)",
        "CREATE INDEX pr_state IF NOT EXISTS FOR (pr:PullRequest) ON (pr.state)",
    ]
    
    # Priority 2: Status and State Indexes
    priority2 = [
        "CREATE INDEX initiative_status IF NOT EXISTS FOR (i:Initiative) ON (i.status)",
        "CREATE INDEX epic_status IF NOT EXISTS FOR (e:Epic) ON (e.status)",
        "CREATE INDEX issue_status IF NOT EXISTS FOR (i:Issue) ON (i.status)",
        "CREATE INDEX issue_type IF NOT EXISTS FOR (i:Issue) ON (i.type)",
        "CREATE INDEX sprint_status IF NOT EXISTS FOR (s:Sprint) ON (s.status)",
        "CREATE INDEX branch_is_default IF NOT EXISTS FOR (b:Branch) ON (b.is_default)",
        "CREATE INDEX branch_is_deleted IF NOT EXISTS FOR (b:Branch) ON (b.is_deleted)",
        "CREATE INDEX branch_is_protected IF NOT EXISTS FOR (b:Branch) ON (b.is_protected)",
        "CREATE INDEX file_is_test IF NOT EXISTS FOR (f:File) ON (f.is_test)",
        "CREATE INDEX pr_mergeable_state IF NOT EXISTS FOR (pr:PullRequest) ON (pr.mergeable_state)",
    ]
    
    # Priority 3: Date/Time Indexes
    priority3 = [
        "CREATE INDEX person_hire_date IF NOT EXISTS FOR (p:Person) ON (p.hire_date)",
        "CREATE INDEX initiative_start_date IF NOT EXISTS FOR (i:Initiative) ON (i.start_date)",
        "CREATE INDEX initiative_due_date IF NOT EXISTS FOR (i:Initiative) ON (i.due_date)",
        "CREATE INDEX epic_start_date IF NOT EXISTS FOR (e:Epic) ON (e.start_date)",
        "CREATE INDEX epic_due_date IF NOT EXISTS FOR (e:Epic) ON (e.due_date)",
        "CREATE INDEX issue_created_at IF NOT EXISTS FOR (i:Issue) ON (i.created_at)",
        "CREATE INDEX sprint_start_date IF NOT EXISTS FOR (s:Sprint) ON (s.start_date)",
        "CREATE INDEX sprint_end_date IF NOT EXISTS FOR (s:Sprint) ON (s.end_date)",
        "CREATE INDEX repository_created_at IF NOT EXISTS FOR (r:Repository) ON (r.created_at)",
        "CREATE INDEX branch_last_commit_timestamp IF NOT EXISTS FOR (b:Branch) ON (b.last_commit_timestamp)",
        "CREATE INDEX branch_created_at IF NOT EXISTS FOR (b:Branch) ON (b.created_at)",
        "CREATE INDEX commit_timestamp IF NOT EXISTS FOR (c:Commit) ON (c.timestamp)",
        "CREATE INDEX file_created_at IF NOT EXISTS FOR (f:File) ON (f.created_at)",
        "CREATE INDEX pr_created_at IF NOT EXISTS FOR (pr:PullRequest) ON (pr.created_at)",
        "CREATE INDEX pr_merged_at IF NOT EXISTS FOR (pr:PullRequest) ON (pr.merged_at)",
        "CREATE INDEX pr_updated_at IF NOT EXISTS FOR (pr:PullRequest) ON (pr.updated_at)",
        "CREATE INDEX pr_closed_at IF NOT EXISTS FOR (pr:PullRequest) ON (pr.closed_at)",
    ]
    
    # Priority 4: Composite Indexes
    priority4 = [
        "CREATE INDEX person_role_seniority IF NOT EXISTS FOR (p:Person) ON (p.role, p.seniority)",
        "CREATE INDEX issue_type_status IF NOT EXISTS FOR (i:Issue) ON (i.type, i.status)",
        "CREATE INDEX issue_status_priority IF NOT EXISTS FOR (i:Issue) ON (i.status, i.priority)",
        "CREATE INDEX branch_is_default_is_deleted IF NOT EXISTS FOR (b:Branch) ON (b.is_default, b.is_deleted)",
        "CREATE INDEX pr_state_created_at IF NOT EXISTS FOR (pr:PullRequest) ON (pr.state, pr.created_at)",
    ]
    
    # Priority 5: Full-Text Search Indexes
    priority5 = [
        "CREATE FULLTEXT INDEX initiative_summary_fulltext IF NOT EXISTS FOR (i:Initiative) ON EACH [i.summary, i.description]",
        "CREATE FULLTEXT INDEX epic_summary_fulltext IF NOT EXISTS FOR (e:Epic) ON EACH [e.summary, e.description]",
        "CREATE FULLTEXT INDEX issue_summary_fulltext IF NOT EXISTS FOR (i:Issue) ON EACH [i.summary, i.description]",
        "CREATE FULLTEXT INDEX pr_title_fulltext IF NOT EXISTS FOR (pr:PullRequest) ON EACH [pr.title, pr.description]",
        "CREATE FULLTEXT INDEX commit_message_fulltext IF NOT EXISTS FOR (c:Commit) ON EACH [c.message]",
    ]
    
    # Priority 6: Range Indexes for Analytics
    priority6 = [
        "CREATE INDEX issue_story_points IF NOT EXISTS FOR (i:Issue) ON (i.story_points)",
        "CREATE INDEX commit_additions IF NOT EXISTS FOR (c:Commit) ON (c.additions)",
        "CREATE INDEX commit_deletions IF NOT EXISTS FOR (c:Commit) ON (c.deletions)",
        "CREATE INDEX commit_files_changed IF NOT EXISTS FOR (c:Commit) ON (c.files_changed)",
        "CREATE INDEX pr_commits_count IF NOT EXISTS FOR (pr:PullRequest) ON (pr.commits_count)",
        "CREATE INDEX pr_additions IF NOT EXISTS FOR (pr:PullRequest) ON (pr.additions)",
        "CREATE INDEX pr_deletions IF NOT EXISTS FOR (pr:PullRequest) ON (pr.deletions)",
        "CREATE INDEX pr_changed_files IF NOT EXISTS FOR (pr:PullRequest) ON (pr.changed_files)",
        "CREATE INDEX pr_comments IF NOT EXISTS FOR (pr:PullRequest) ON (pr.comments)",
        "CREATE INDEX pr_review_comments IF NOT EXISTS FOR (pr:PullRequest) ON (pr.review_comments)",
        "CREATE INDEX file_size IF NOT EXISTS FOR (f:File) ON (f.size)",
    ]
    
    # Priority 7: Relationship Property Indexes
    priority7 = [
        "CREATE INDEX FOR ()-[c:COLLABORATOR]-() ON (c.permission)",
        "CREATE INDEX FOR ()-[r:REVIEWED_BY]-() ON (r.state)",
    ]
    
    all_indexes = {
        "Priority 1: High-Impact Lookups (Critical)": priority1,
        "Priority 2: Status and State (High)": priority2,
        "Priority 3: Date/Time (Medium-High)": priority3,
        # "Priority 4: Composite Indexes (Medium)": priority4,
        # "Priority 5: Full-Text Search (Medium)": priority5,
        # "Priority 6: Analytics (Low-Medium)": priority6,
        # "Priority 7: Relationship Properties (Low)": priority7,
    }
    
    try:
        with driver.session() as session:
            # Test connection
            try:
                session.run("RETURN 1")
            except Exception as e:
                print(f"❌ Failed to connect to Neo4j at {NEO4J_URI}")
                print(f"   Error: {str(e)}")
                print("\nPlease ensure:")
                print("  1. Neo4j is running (docker compose up -d)")
                print("  2. Connection details are correct")
                sys.exit(1)
            
            total_created = 0
            total_existing = 0
            total_failed = 0
            
            for priority_name, indexes in all_indexes.items():
                print(f"\n{'=' * 70}")
                print(f"{priority_name}")
                print('=' * 70)
                
                for idx_query in indexes:
                    try:
                        session.run(idx_query)
                        index_name = idx_query.split("INDEX")[1].split("IF NOT EXISTS")[0].strip()
                        print(f"✓ Created: {index_name}")
                        total_created += 1
                    except Exception as e:
                        error_msg = str(e).lower()
                        if "already exists" in error_msg or "equivalent" in error_msg:
                            index_name = idx_query.split("INDEX")[1].split("IF NOT EXISTS")[0].strip()
                            print(f"- Exists: {index_name}")
                            total_existing += 1
                        else:
                            index_name = idx_query.split("INDEX")[1].split("IF NOT EXISTS")[0].strip() if "INDEX" in idx_query else "Unknown"
                            print(f"✗ Failed: {index_name}")
                            print(f"  Error: {str(e)}")
                            total_failed += 1
            
            print(f"\n{'=' * 70}")
            print("SUMMARY")
            print('=' * 70)
            print(f"✓ Indexes created: {total_created}")
            print(f"- Already existing: {total_existing}")
            print(f"✗ Failed: {total_failed}")
            print(f"📊 Total indexes: {total_created + total_existing}")
            
            if total_failed > 0:
                print(f"\n⚠️  {total_failed} index(es) failed to create. Check errors above.")
                sys.exit(1)
            
    finally:
        driver.close()


if __name__ == "__main__":
    print("=" * 70)
    print("Creating Recommended Indexes for Project Graph Database")
    print("=" * 70)
    print(f"\nConnecting to: {NEO4J_URI}")
    print(f"User: {NEO4J_USER}\n")
    
    try:
        create_indexes()
        print("\n✅ Index creation complete!")
        print("\nVerify indexes with:")
        print("  SHOW INDEXES;")
    except KeyboardInterrupt:
        print("\n\n⚠️  Index creation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)
