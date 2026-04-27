#!/usr/bin/env python3
"""
Find stub nodes that were created from cross-module references but not yet enriched.

Stub Issues: Created when commits reference Jira issue keys (from branch names or commit messages)
             but those issues haven't been loaded from Jira yet.

Stub Teams:  Created when Jira Epics reference team names but those teams haven't been loaded
             from GitHub yet.

This script helps identify which nodes need to be loaded from the other system, or which
references might be invalid.
"""

import os
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def find_stub_issues(session):
    """Find Issue nodes that are still stubs (created by GitHub but not enriched by Jira)."""
    query = """
    MATCH (i:Issue)
    WHERE i.source = 'github_reference'
    OPTIONAL MATCH (i)<-[:REFERENCES]-(c:Commit)
    RETURN i.key as issue_key, 
           i.id as issue_id,
           i.created_at as created_at,
           count(c) as commit_references
    ORDER BY commit_references DESC, issue_key
    """
    return list(session.run(query))


def find_enriched_issues(session):
    """Find Issue nodes that were stubs but have been enriched by Jira."""
    query = """
    MATCH (i:Issue)
    WHERE i.source = 'jira' AND i.summary IS NOT NULL
    OPTIONAL MATCH (i)<-[:REFERENCES]-(c:Commit)
    RETURN i.key as issue_key,
           i.summary as summary,
           i.status as status,
           count(c) as commit_references
    ORDER BY commit_references DESC
    LIMIT 20
    """
    return list(session.run(query))


def find_stub_teams(session):
    """Find Team nodes that are still stubs (created by Jira but not enriched by GitHub)."""
    query = """
    MATCH (t:Team)
    WHERE t.source = 'jira_reference'
    OPTIONAL MATCH (t)-[:TEAM]-(e:Epic)
    RETURN t.name as team_name, 
           t.id as team_id,
           t.created_at as created_at,
           count(e) as epic_references
    ORDER BY epic_references DESC, team_name
    """
    return list(session.run(query))


def find_enriched_teams(session):
    """Find Team nodes that were stubs but have been enriched by GitHub."""
    query = """
    MATCH (t:Team)
    WHERE t.source = 'github'
    OPTIONAL MATCH (t)-[:TEAM]-(e:Epic)
    OPTIONAL MATCH (t)-[:MEMBER_OF]-(p:Person)
    RETURN t.name as team_name,
           count(DISTINCT e) as epic_references,
           count(DISTINCT p) as members
    ORDER BY epic_references DESC
    LIMIT 20
    """
    return list(session.run(query))


def get_node_statistics(session, node_type):
    """Get overall statistics about nodes by source."""
    query = f"""
    MATCH (n:{node_type})
    RETURN n.source as source,
           count(n) as count
    ORDER BY count DESC
    """
    return list(session.run(query))


def main():
    """Run diagnostics on stub nodes."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    
    print("=" * 80)
    print("STUB NODE DIAGNOSTIC - Cross-Module Reference Analysis")
    print("=" * 80)
    
    with driver.session() as session:
        # ===== ISSUE STATISTICS =====
        print("\n📊 ISSUE Statistics by Source:")
        print("-" * 80)
        stats = get_node_statistics(session, "Issue")
        
        total_issues = 0
        for record in stats:
            source = record['source'] or 'null'
            count = record['count']
            total_issues += count
            
            if source == 'github_reference':
                status = "⚠️  Stub (waiting for Jira)"
            elif source == 'jira':
                status = "✓  Enriched by Jira"
            else:
                status = "❓ Unknown source"
            
            print(f"  {source:20s}: {count:5d} issues - {status}")
        
        print(f"\n  {'Total':20s}: {total_issues:5d} issues")
        
        # Find stub issues
        print("\n" + "=" * 80)
        print("⚠️  STUB ISSUES (Created from GitHub, not yet enriched by Jira)")
        print("=" * 80)
        
        stubs = find_stub_issues(session)
        
        if not stubs:
            print("\n✓ No stub issues found! All referenced issues have been loaded from Jira.")
        else:
            print(f"\nFound {len(stubs)} stub issue(s):\n")
            print(f"{'Issue Key':<15} {'Commit Refs':<12} {'Created At':<30}")
            print("-" * 80)
            
            for record in stubs:
                issue_key = record['issue_key']
                refs = record['commit_references']
                created_at = record['created_at'].to_native() if record['created_at'] else 'N/A'
                print(f"{issue_key:<15} {refs:<12} {str(created_at):<30}")
            
            print("\n💡 Recommendations:")
            print("  1. Load these issues from Jira using: python modules/jira/main.py")
            print("  2. If issues don't exist in Jira, they may be typos in branch/commit names")
        
        # Show sample of enriched issues
        print("\n" + "=" * 80)
        print("✓ SAMPLE ENRICHED ISSUES (Loaded from Jira with commit references)")
        print("=" * 80)
        
        enriched = find_enriched_issues(session)
        
        if not enriched:
            print("\nNo enriched issues found yet. Run: python modules/jira/main.py")
        else:
            print(f"\nShowing top {len(enriched)} enriched issues:\n")
            print(f"{'Issue Key':<12} {'Status':<12} {'Refs':<6} {'Summary':<50}")
            print("-" * 80)
            
            for record in enriched:
                issue_key = record['issue_key']
                summary = (record['summary'] or 'N/A')[:47] + '...' if len(record['summary'] or '') > 50 else (record['summary'] or 'N/A')
                status = record['status'] or 'N/A'
                refs = record['commit_references']
                print(f"{issue_key:<12} {status:<12} {refs:<6} {summary:<50}")
        
        # ===== TEAM STATISTICS =====
        print("\n\n" + "=" * 80)
        print("📊 TEAM Statistics by Source:")
        print("=" * 80)
        team_stats = get_node_statistics(session, "Team")
        
        total_teams = 0
        for record in team_stats:
            source = record['source'] or 'null'
            count = record['count']
            total_teams += count
            
            if source == 'jira_reference':
                status = "⚠️  Stub (waiting for GitHub)"
            elif source == 'github':
                status = "✓  Enriched by GitHub"
            else:
                status = "❓ Unknown source"
            
            print(f"  {source:20s}: {count:5d} teams - {status}")
        
        print(f"\n  {'Total':20s}: {total_teams:5d} teams")
        
        # Find stub teams
        print("\n" + "=" * 80)
        print("⚠️  STUB TEAMS (Created from Jira, not yet enriched by GitHub)")
        print("=" * 80)
        
        stub_teams = find_stub_teams(session)
        
        if not stub_teams:
            print("\n✓ No stub teams found! All referenced teams have been loaded from GitHub.")
        else:
            print(f"\nFound {len(stub_teams)} stub team(s):\n")
            print(f"{'Team Name':<30} {'Epic Refs':<12} {'Created At':<30}")
            print("-" * 80)
            
            for record in stub_teams:
                team_name = record['team_name']
                refs = record['epic_references']
                created_at = record['created_at'].to_native() if record['created_at'] else 'N/A'
                print(f"{team_name:<30} {refs:<12} {str(created_at):<30}")
            
            print("\n💡 Recommendations:")
            print("  1. Load these teams from GitHub using: python modules/github/main.py")
            print("  2. If teams don't exist in GitHub, they may be incorrect in Jira Epic metadata")
        
        # Show sample of enriched teams
        print("\n" + "=" * 80)
        print("✓ SAMPLE ENRICHED TEAMS (Loaded from GitHub with Epic references)")
        print("=" * 80)
        
        enriched_teams = find_enriched_teams(session)
        
        if not enriched_teams:
            print("\nNo enriched teams found yet. Run: python modules/github/main.py")
        else:
            print(f"\nShowing top {len(enriched_teams)} enriched teams:\n")
            print(f"{'Team Name':<30} {'Epics':<8} {'Members':<8}")
            print("-" * 60)
            
            for record in enriched_teams:
                team_name = (record['team_name'] or 'N/A')[:29]
                epics = record['epic_references']
                members = record['members']
                print(f"{team_name:<30} {epics:<8} {members:<8}")
        
        print("\n" + "=" * 80)
        print("\n✓ Diagnostic complete")
        print("\nSUMMARY:")
        print(f"  Issues: {total_issues} total")
        if stubs:
            print(f"    ⚠️  {len(stubs)} stub issue(s) waiting for Jira")
        print(f"  Teams: {total_teams} total")
        if stub_teams:
            print(f"    ⚠️  {len(stub_teams)} stub team(s) waiting for GitHub")
        
        if not stubs and not stub_teams:
            print("\n✅ All stubs have been enriched! No pending cross-module references.")
        else:
            print("\n💡 Run the corresponding module to enrich stub nodes.")
    
    driver.close()


if __name__ == "__main__":
    main()
