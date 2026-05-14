"""
Neo4j Models and Utilities for Project Graph
Provides dataclasses for all layers and utility functions for merging into Neo4j.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any
from neo4j import Session


def _has_value(props: Dict[str, Any], key: str) -> bool:
    """Return True when a property exists and is meaningfully populated."""
    if key not in props:
        return False
    value = props.get(key)
    if value is None:
        return False
    if value == "":
        return False
    if value == []:
        return False
    return True


# ============================================================================
# LAYER 1: People & Teams
# ============================================================================

@dataclass
class Person:
    """Person node in the organizational graph."""
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    title: Optional[str] = None
    role: Optional[str] = None
    seniority: Optional[str] = None
    is_manager: Optional[bool] = None
    hire_date: Optional[str] = None
    url: Optional[str] = None

    def to_neo4j_properties(self) -> Dict[str, Any]:
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Person object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"PERSON: {self.name}")
        print(f"{'='*60}")
        print(f"  ID:         {self.id}")
        print(f"  Email:      {self.email}")
        print(f"  Title:      {self.title}")
        print(f"  Role:       {self.role}")
        print(f"  Seniority:  {self.seniority}")
        print(f"  Hire Date:  {self.hire_date}")
        print(f"  Is Manager: {self.is_manager}")
        if self.url:
            print(f"  URL:        {self.url}")
        print(f"{'='*60}\n")


@dataclass
class Team:
    """Team node in the organizational graph."""
    id: str
    name: Optional[str] = None
    target_size: Optional[int] = None
    source: Optional[str] = None
    created_at: Optional[str] = None
    url: Optional[str] = None

    def to_neo4j_properties(self) -> Dict[str, Any]:
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Team object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"TEAM: {self.name}")
        print(f"{'='*60}")
        print(f"  ID:          {self.id}")
        print(f"  Target Size: {self.target_size}")
        print(f"  Created At:  {self.created_at}")
        if self.url:
            print(f"  URL:         {self.url}")
        print(f"{'='*60}\n")


@dataclass
class IdentityMapping:
    """Identity mapping node linking external provider identities to Person.
    
    This represents an external identity (GitHub, Jira, etc.) that maps to a Person.
    Multiple IdentityMapping nodes can point to the same Person via MAPS_TO relationships.
    
    Note: The 'person_id' field is NOT part of this dataclass. In batch loading scenarios
    where JSON includes person_id, that field should be extracted separately and used to
    create the MAPS_TO relationship.
    
    Example:
        identity = IdentityMapping(
            id="identity_github_alice",
            provider="GitHub",
            username="alicej",
            email="alice@company.com",
            last_updated_at="2026-02-04T10:30:00Z"
        )
        
        rel = Relationship(
            type="MAPS_TO",
            from_id=identity.id,
            to_id="person_alice",  # This is the person_id
            from_type="IdentityMapping",
            to_type="Person"
        )
        
        merge_identity_mapping(session, identity, relationships=[rel])
    """
    id: str
    provider: str
    username: str
    email: Optional[str] = None
    last_updated_at: Optional[str] = None

    def to_neo4j_properties(self) -> Dict[str, Any]:
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the IdentityMapping object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"IDENTITY MAPPING: {self.username}@{self.provider}")
        print(f"{'='*60}")
        print(f"  ID:       {self.id}")
        print(f"  Provider: {self.provider}")
        print(f"  Username: {self.username}")
        print(f"  Email:    {self.email}")
        print(f"{'='*60}\n")


# ============================================================================
# LAYER 2: Jira Initiatives
# ============================================================================

@dataclass
class Project:
    """Project node representing a Jira project."""
    id: str
    key: str
    name: str
    status: Optional[str] = None
    project_type: Optional[str] = None  # e.g., "software", "business"
    url: Optional[str] = None  # URL to view the project in Jira
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        props = asdict(self)
        # Remove None values for cleaner storage
        return {k: v for k, v in props.items() if v is not None}
    
    def print_cli(self) -> None:
        """Print the Project object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"PROJECT: {self.name}")
        print(f"{'='*60}")
        print(f"  ID:          {self.id}")
        print(f"  Key:         {self.key}")
        if self.status:
            print(f"  Status:      {self.status}")
        if self.project_type:
            print(f"  Type:        {self.project_type}")
        print(f"{'='*60}\n")


@dataclass
class JiraIssueBase:
    """Base dataclass for all Jira issue types (Initiative, Epic, Story, Bug, etc).
    
    Contains common fields that all Jira issues share. Specific issue types can extend this.
    
    Note: User relationship fields like 'assignee', 'reporter' are NOT part of this dataclass.
    They should be extracted separately and used to create relationships to Person nodes.
    """
    id: str
    key: str
    summary: str
    priority: str
    status: str
    created_at: str              # ISO format string (YYYY-MM-DD)
    updated_at: str              # ISO format string (YYYY-MM-DD)
    duedate: Optional[str] = None    # ISO format string (YYYY-MM-DD), can be None
    project_id: Optional[str] = None  # Project ID for PART_OF relationship
    labels: Optional[List[str]] = field(default_factory=list)
    components: Optional[List[str]] = field(default_factory=list)
    url: Optional[str] = None  # URL to view the issue in Jira
    _last_synced_at: Optional[str] = None  # ISO format datetime string - tracks last successful sync
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        props = asdict(self)
        # Remove None values and empty lists for cleaner storage
        return {k: v for k, v in props.items() if v is not None and v != []}
    
    def print_cli(self) -> None:
        """Print the Jira issue in an easy-to-read CLI format."""
        issue_type = self.__class__.__name__
        print(f"\n{'='*60}")
        print(f"{issue_type.upper()}: {self.summary}")
        print(f"{'='*60}")
        print(f"  ID:         {self.id}")
        print(f"  Key:        {self.key}")
        print(f"  Priority:   {self.priority}")
        print(f"  Status:     {self.status}")
        print(f"  Created:    {self.created_at}")
        print(f"  Updated:    {self.updated_at}")
        if self.duedate:
            print(f"  Due Date:   {self.duedate}")
        if self.labels:
            print(f"  Labels:     {', '.join(self.labels)}")
        if self.components:
            print(f"  Components: {', '.join(self.components)}")
        print(f"{'='*60}\n")


@dataclass
class Initiative(JiraIssueBase):
    """Initiative node representing a high-level Jira work item.
    
    Extends JiraIssueBase with all common Jira fields.
    
    Note: The 'assignee' and 'reporter' user objects are NOT part of this dataclass.
    They should be extracted and used to create ASSIGNED_TO and REPORTED_BY
    relationships directly to Person nodes.
    
    Example:
        initiative = Initiative(
            id="initiative_init_1",
            key="INIT-1",
            summary="Platform Modernization",
            priority="High",
            status="In Progress",
            created_at="2025-12-01",
            updated_at="2026-01-15",
            duedate="2026-06-30",
            project_id="project_eng_2026",
            labels=["platform", "kubernetes"],
            components=["Infrastructure"]
        )
        
        # Relationships point directly to Person nodes
        assignee_rel = Relationship(
            type="ASSIGNED_TO",
            from_id=initiative.id,
            to_id="person_jira_abc123",  # Person node ID
            from_type="Initiative",
            to_type="Person"
        )
    """
    pass


@dataclass
class Epic:
    """Epic node representing a Jira Epic.
    
    Note: The 'assignee_id', 'team_id', and 'initiative_id' fields are NOT part of this dataclass.
    They should be extracted from JSON and used to create relationships:
    - ASSIGNED_TO (undirected) - Person
    - TEAM (undirected) - Team
    - PART_OF -> Initiative
    
    Example:
        epic = Epic(
            id="epic_plat_1",
            key="PLAT-1",
            summary="Migrate to Kubernetes",
            ...
        )
        
        # Relationships point directly to Person, Team, and Initiative nodes
        assignee_rel = Relationship(
            type="ASSIGNED_TO",
            from_id=epic.id,
            to_id="person_alice",
            from_type="Epic",
            to_type="Person"
        )
    """
    id: str
    key: str
    summary: str
    priority: str
    status: str
    start_date: str   # ISO format string (YYYY-MM-DD)
    due_date: str     # ISO format string (YYYY-MM-DD)
    created_at: str   # ISO format string (YYYY-MM-DD)
    updated_at: Optional[str] = None  # ISO format string (YYYY-MM-DD)
    url: Optional[str] = None
    _last_synced_at: Optional[str] = None  # ISO format datetime string - tracks last successful sync
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Epic object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"EPIC: {self.summary}")
        print(f"{'='*60}")
        print(f"  ID:          {self.id}")
        print(f"  Key:         {self.key}")
        print(f"  Priority:    {self.priority}")
        print(f"  Status:      {self.status}")
        print(f"  Start Date:  {self.start_date}")
        print(f"  Due Date:    {self.due_date}")
        print(f"  Created At:  {self.created_at}")
        if self.url:
            print(f"  URL:         {self.url}")
        print(f"{'='*60}\n")


@dataclass
class Issue:
    """Issue node representing a Jira work item (Story, Bug, or Task).
    
    Note: The 'epic_id', 'assignee_id', 'reporter_id', and 'related_story_id' fields
    are NOT part of this dataclass. They should be extracted from JSON and used to
    create relationships:
    - PART_OF -> Epic
    - ASSIGNED_TO (undirected) - Person
    - REPORTED_BY (undirected) - Person
    - RELATES_TO (undirected) - Issue (for bugs related to stories)
    
    Example:
        issue = Issue(
            id="issue_plat_1",
            key="PLAT-1",
            type="Story",
            summary="Implement Kubernetes deployment",
            ...
        )
        
        # Relationships point directly to Epic, Person nodes
        epic_rel = Relationship(
            type="PART_OF",
            from_id=issue.id,
            to_id="epic_plat_1",
            from_type="Issue",
            to_type="Epic"
        )
    """
    id: str
    key: str
    type: str         # "Story", "Bug", or "Task"
    summary: str
    priority: str
    status: str
    story_points: int
    created_at: str   # ISO format datetime string
    updated_at: Optional[str] = None  # ISO format datetime string
    url: Optional[str] = None
    _last_synced_at: Optional[str] = None  # ISO format datetime string - tracks last successful sync
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Issue object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"ISSUE [{self.type}]: {self.summary}")
        print(f"{'='*60}")
        print(f"  ID:            {self.id}")
        print(f"  Key:           {self.key}")
        print(f"  Priority:      {self.priority}")
        print(f"  Status:        {self.status}")
        print(f"  Story Points:  {self.story_points}")
        print(f"  Created At:    {self.created_at}")
        if self.url:
            print(f"  URL:           {self.url}")
        print(f"{'='*60}\n")


@dataclass
class Sprint:
    """Sprint node representing a time-boxed iteration.
    
    Example:
        sprint = Sprint(
            id="sprint_1",
            name="Sprint 1",
            goal="Platform infrastructure foundations",
            start_date="2025-12-09",
            end_date="2025-12-20",
            status="Completed"
        )
    """
    id: str
    name: str
    goal: str
    start_date: str   # ISO format string (YYYY-MM-DD)
    end_date: str     # ISO format string (YYYY-MM-DD)
    status: str
    url: Optional[str] = None
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Sprint object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"SPRINT: {self.name}")
        print(f"{'='*60}")
        print(f"  ID:         {self.id}")
        print(f"  Goal:       {self.goal[:50]}..." if len(self.goal) > 50 else f"  Goal:       {self.goal}")
        print(f"  Start Date: {self.start_date}")
        print(f"  End Date:   {self.end_date}")
        print(f"  Status:     {self.status}")
        if self.url:
            print(f"  URL:        {self.url}")
        print(f"{'='*60}\n")


@dataclass
class Repository:
    """Repository node representing a Git repository.
    
    Note: Relationships (COLLABORATOR from Team/Person) are handled separately
    and may include properties like permission, granted_at, role.
    
    Example:
        repository = Repository(
            id="repo_api_gateway",
            name="gateway",
            full_name="company/gateway",
            url="https://github.com/company/gateway",
            language="Python",
            is_private=True,
            topics=["api", "gateway", "python"],
            created_at="2023-11-10",
            _last_synced_at="2026-02-04T10:30:00Z"
        )
        
        # COLLABORATOR relationships with properties
        collab_rel = Relationship(
            type="COLLABORATOR",
            from_id="team_api_team",
            to_id=repository.id,
            from_type="Team",
            to_type="Repository",
            properties={"permission": "WRITE", "granted_at": "2023-11-10"}
        )
    """
    id: str
    name: str
    full_name: str
    url: str
    language: str
    is_private: bool
    topics: List[str]      # List of topic strings
    created_at: str  # ISO format string (YYYY-MM-DD)
    _last_synced_at: Optional[str] = None  # ISO format datetime string - tracks last successful sync
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Repository object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"REPOSITORY: {self.full_name}")
        print(f"{'='*60}")
        print(f"  ID:          {self.id}")
        print(f"  Name:        {self.name}")
        print(f"  URL:         {self.url}")
        print(f"  Language:    {self.language}")
        print(f"  Is Private:  {self.is_private}")
        print(f"  Topics:      {', '.join(self.topics) if self.topics else 'None'}")
        print(f"  Created At:  {self.created_at}")
        print(f"{'='*60}\n")


@dataclass
class Branch:
    """Branch node representing a Git branch.
    
    Note: We do not track branch creation timestamp (created_at) because:
    1. GitHub API does not provide direct access to branch ref creation time
    2. Finding it requires iterating through ALL commits on the branch (extremely slow)
    3. For main branches with 10K+ commits, this takes minutes per branch
    4. last_commit_timestamp is sufficient for identifying stale branches
    
    Example:
        branch = Branch(
            id="branch_main_repo_api",
            name="main",
            is_default=True,
            is_protected=True,
            is_deleted=False,
            is_external=False,
            last_commit_sha="abc123def",
            last_commit_timestamp="2026-01-17T10:30:00"
        )
        
        # BRANCH_OF relationship
        branch_rel = Relationship(
            type="BRANCH_OF",
            from_id=branch.id,
            to_id="repo_api_gateway",
            from_type="Branch",
            to_type="Repository"
        )
    """
    id: str
    name: str
    is_default: bool
    is_protected: bool
    is_deleted: bool
    is_external: bool           # True if branch is from a fork
    last_commit_sha: str
    last_commit_timestamp: str  # ISO format datetime string
    url: Optional[str] = None   # GitHub URL to view branch in browser
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Branch object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"BRANCH: {self.name}")
        print(f"{'='*60}")
        print(f"  ID:                   {self.id}")
        print(f"  Is Default:           {self.is_default}")
        print(f"  Is Protected:         {self.is_protected}")
        print(f"  Is Deleted:           {self.is_deleted}")
        print(f"  Is External:          {self.is_external}")
        print(f"  Last Commit SHA:      {self.last_commit_sha[:10]}..." if len(self.last_commit_sha) > 10 else f"  Last Commit SHA:      {self.last_commit_sha}")
        print(f"  Last Commit Time:     {self.last_commit_timestamp}")
        print(f"{'='*60}\n")


@dataclass
class Commit:
    """Commit node representing a Git commit.
    
    Example:
        commit = Commit(
            id="commit_1",
            sha="a1b2c3d4e5f6789...",
            message="[PROJ-123] Fix authentication bug",
            created_at="2026-01-15T14:30:00",
            additions=45,
            deletions=12,
            files_changed=3
        )
        
        # Relationships
        part_of_rel = Relationship(
            type="PART_OF",
            from_id=commit.id,
            to_id="branch_main_repo_api",
            from_type="Commit",
            to_type="Branch"
        )
        
        authored_by_rel = Relationship(
            type="AUTHORED_BY",
            from_id=commit.id,
            to_id="person_alice",
            from_type="Commit",
            to_type="Person"
        )
        
        modifies_rel = Relationship(
            type="MODIFIES",
            from_id=commit.id,
            to_id="file_42",
            from_type="Commit",
            to_type="File",
            properties={"additions": 25, "deletions": 8}
        )
    """
    id: str
    sha: str
    message: str
    created_at: str  # ISO format datetime string
    additions: int
    deletions: int
    files_changed: int
    url: Optional[str] = None  # GitHub URL to view commit in browser
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the Commit object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"COMMIT: {self.message[:40]}..." if len(self.message) > 40 else f"COMMIT: {self.message}")
        print(f"{'='*60}")
        print(f"  ID:            {self.id}")
        print(f"  SHA:           {self.sha[:10]}..." if len(self.sha) > 10 else f"  SHA:           {self.sha}")
        print(f"  Created At:    {self.created_at}")
        print(f"  Additions:     {self.additions}")
        print(f"  Deletions:     {self.deletions}")
        print(f"  Files Changed: {self.files_changed}")
        print(f"{'='*60}\n")


@dataclass
class File:
    """File node representing a file in a repository.
    
    Example:
        file = File(
            id="file_42",
            path="src/services/UserService.ts",
            name="UserService.ts",
            extension=".ts",
            language="TypeScript",
            is_test=False,
            size=3420,
            created_at="2025-10-11T09:00:00",
            url="https://github.com/owner/repo/blob/main/src/services/UserService.ts"
        )
    """
    id: str
    path: str
    name: str
    extension: str
    language: str
    is_test: bool
    size: int
    created_at: str  # ISO format datetime string
    url: Optional[str] = None  # GitHub URL to view file in browser
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the File object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"FILE: {self.name}")
        print(f"{'='*60}")
        print(f"  ID:         {self.id}")
        print(f"  Path:       {self.path}")
        print(f"  Extension:  {self.extension}")
        print(f"  Language:   {self.language}")
        print(f"  Is Test:    {self.is_test}")
        print(f"  Size:       {self.size} bytes")
        print(f"  Created At: {self.created_at}")
        print(f"{'='*60}\n")


@dataclass
class PullRequest:
    """PullRequest node representing a GitHub/GitLab pull/merge request.
    
    Example:
        pr = PullRequest(
            id="pr_repo_1",
            number=42,
            title="feat: Add authentication",
            state="merged",
            created_at="2026-01-10T14:30:00",
            updated_at="2026-01-15T16:20:00",
            merged_at="2026-01-15T16:20:00",
            closed_at="2026-01-15T16:20:00",
            commits_count=5,
            additions=250,
            deletions=30,
            changed_files=8,
            comments=3,
            review_comments=12,
            head_branch_name="feature/oauth",
            base_branch_name="main",
            labels=["enhancement", "security"],
            mergeable_state="clean",
            url="https://github.com/owner/repo/pull/42"
        )
        
        # Relationships
        created_by_rel = Relationship(
            type="CREATED_BY",
            from_id=pr.id,
            to_id="person_alice",
            from_type="PullRequest",
            to_type="Person"
        )
        
        reviewed_by_rel = Relationship(
            type="REVIEWED_BY",
            from_id=pr.id,
            to_id="person_bob",
            from_type="PullRequest",
            to_type="Person",
            properties={"state": "APPROVED"}
        )
    """
    id: str
    number: int
    title: str
    state: str  # "open", "merged", "closed"
    created_at: str
    updated_at: str
    merged_at: Optional[str]  # Nullable - only for merged PRs
    closed_at: Optional[str]  # Nullable - for merged or closed PRs
    commits_count: int
    additions: int
    deletions: int
    changed_files: int
    comments: int
    review_comments: int
    head_branch_name: str
    base_branch_name: str
    labels: List[str]   # List of label strings
    mergeable_state: str
    url: Optional[str] = None  # GitHub URL to view PR in browser
    
    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Convert to Neo4j properties."""
        return asdict(self)
    
    def print_cli(self) -> None:
        """Print the PullRequest object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"PULL REQUEST #{self.number}: {self.title}")
        print(f"{'='*60}")
        print(f"  ID:               {self.id}")
        print(f"  State:            {self.state}")
        print(f"  Created At:       {self.created_at}")
        print(f"  Updated At:       {self.updated_at}")
        print(f"  Merged At:        {self.merged_at or 'N/A'}")
        print(f"  Closed At:        {self.closed_at or 'N/A'}")
        print(f"  Branches:         {self.head_branch_name} → {self.base_branch_name}")
        print(f"  Commits:          {self.commits_count}")
        print(f"  Changes:          +{self.additions} -{self.deletions} ({self.changed_files} files)")
        print(f"  Comments:         {self.comments} ({self.review_comments} in review)")
        print(f"  Labels:           {', '.join(self.labels) if self.labels else 'None'}")
        print(f"  Mergeable State:  {self.mergeable_state}")
        print(f"{'='*60}\n")


# ============================================================================
# RELATIONSHIP DATACLASS
# ============================================================================

@dataclass
class Relationship:
    """Represents a relationship between two nodes."""
    type: str
    from_id: str
    to_id: str
    from_type: str
    to_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def print_cli(self) -> None:
        """Print the Relationship object in an easy-to-read CLI format."""
        print(f"\n{'='*60}")
        print(f"RELATIONSHIP: {self.type}")
        print(f"{'='*60}")
        print(f"  From: ({self.from_type}) {self.from_id}")
        print(f"  To:   ({self.to_type}) {self.to_id}")
        if self.properties:
            print(f"  Properties:")
            for key, value in self.properties.items():
                print(f"    - {key}: {value}")
        print(f"{'='*60}\n")


# ============================================================================
# RELATIONSHIP DIRECTIONALITY
# ============================================================================

# Relationships that should store a single edge and be queried as undirected.
UNDIRECTED_RELATIONSHIPS = {
    # Layer 1
    "MEMBER_OF",        # Person ↔ Team
    "MAPS_TO",          # IdentityMapping ↔ Person
    
    # Layer 2
    "ASSIGNED_TO",      # Initiative ↔ Person
    "REPORTED_BY",      # Initiative ↔ Person
    
    # Layer 3
    "TEAM",             # Epic ↔ Team
    
    # Layer 4
    "RELATES_TO",       # Issue ↔ Issue (symmetric)
    
    # Layer 5
    "COLLABORATOR",     # Team/Person ↔ Repository
    
    # Layer 6
    "BRANCH_OF",        # Branch ↔ Repository
    
    # Layer 7
    "AUTHORED_BY",      # Commit ↔ Person
}

# Directional relationships that should create explicit reverse edges.
DIRECTIONAL_RELATIONSHIPS = {
    # Layer 1
    "REPORTS_TO": "MANAGES",        # Person → Person (reports to) / Person ← Person (manages)
    "MANAGES": "MANAGED_BY",        # Person → Team (manages) / Team ← Person (managed by)
    
    # Layer 2
    "PART_OF": "CONTAINS",          # Initiative → Project / Project ← Initiative
    
    # Layer 4
    "IN_SPRINT": "CONTAINS",        # Issue → Sprint / Sprint ← Issue
    "BLOCKS": "BLOCKED_BY",         # Issue → Issue (blocks) / Issue ← Issue (blocked by)
    "DEPENDS_ON": "DEPENDENCY_OF",  # Issue → Issue (depends on) / Issue ← Issue (dependency of)
    
    # Layer 7
    "MODIFIES": "MODIFIED_BY",      # Commit → File (modifies) / File ← Commit (modified by) - with properties
    "REFERENCES": "REFERENCED_BY",  # Commit → Issue (references) / Issue ← Commit (referenced by)
    
    # Layer 8
    "INCLUDES": "INCLUDED_IN",      # PullRequest → Commit (includes) / Commit ← PullRequest (included in)
    "TARGETS": "TARGETED_BY",       # PullRequest → Branch (targets) / Branch ← PullRequest (targeted by)
    "CREATED_BY": "CREATED",        # PullRequest → Person (created by) / Person ← PullRequest (created)
    "REVIEWED_BY": "REVIEWED",      # PullRequest → Person (reviewed by) / Person ← PullRequest (reviewed) - with state property
    "REQUESTED_REVIEWER": "REVIEW_REQUESTED_BY",  # PullRequest → Person / Person ← PullRequest
    "MERGED_BY": "MERGED",          # PullRequest → Person (merged by) / Person ← PullRequest (merged)
}


# ============================================================================
# CONSTRAINT MANAGEMENT
# ============================================================================

def create_constraints(session: Session, layers: Optional[List[int]] = None) -> None:
    """Create uniqueness constraints for node types.
    
    Args:
        session: Neo4j session
        layers: Optional list of layer numbers to create constraints for.
                If None, creates constraints for all layers.
    """
    all_constraints = {
        1: [
            "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT person_email IF NOT EXISTS FOR (p:Person) REQUIRE p.email IS UNIQUE",
            "CREATE CONSTRAINT team_id IF NOT EXISTS FOR (t:Team) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT identity_id IF NOT EXISTS FOR (i:IdentityMapping) REQUIRE i.id IS UNIQUE"
        ],
        2: [
            "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT initiative_id IF NOT EXISTS FOR (i:Initiative) REQUIRE i.id IS UNIQUE"
        ],
        3: [
            "CREATE CONSTRAINT epic_id IF NOT EXISTS FOR (e:Epic) REQUIRE e.id IS UNIQUE"
        ],
        4: [
            "CREATE CONSTRAINT issue_id IF NOT EXISTS FOR (i:Issue) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT sprint_id IF NOT EXISTS FOR (s:Sprint) REQUIRE s.id IS UNIQUE"
        ],
        5: [
            "CREATE CONSTRAINT repository_id IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE"
        ],
        6: [
            "CREATE CONSTRAINT branch_id IF NOT EXISTS FOR (b:Branch) REQUIRE b.id IS UNIQUE"
        ],
        7: [
            "CREATE CONSTRAINT commit_id IF NOT EXISTS FOR (c:Commit) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT commit_sha IF NOT EXISTS FOR (c:Commit) REQUIRE c.sha IS UNIQUE",
            "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.id IS UNIQUE"
        ],
        8: [
            "CREATE CONSTRAINT pull_request_id IF NOT EXISTS FOR (pr:PullRequest) REQUIRE pr.id IS UNIQUE"
        ]
    }
    
    # Determine which constraints to create
    constraints: List[str] = []
    if layers is None:
        for layer_constraints in all_constraints.values():
            constraints.extend(layer_constraints)
    else:
        for layer in layers:
            constraints.extend(all_constraints.get(layer, []))

    for constraint in constraints:
        session.run(constraint)


# ============================================================================
# LAYER 1 MERGE FUNCTIONS
# ============================================================================

def merge_person(session: Session, person: Person, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Person node into Neo4j.
    
    Args:
        session: Neo4j session
        person: Person dataclass instance
        relationships: Optional list of relationships to create
    """
    props = person.to_neo4j_properties()
    
    # MERGE the Person node
    # Build SET clause dynamically for optional fields (additive updates only)
    set_clauses = []
    if _has_value(props, 'name'):
        set_clauses.append("p.name = $name")
    if _has_value(props, 'title'):
        set_clauses.append("p.title = $title")
    if _has_value(props, 'role'):
        set_clauses.append("p.role = $role")
    if _has_value(props, 'seniority'):
        set_clauses.append("p.seniority = $seniority")
    if _has_value(props, 'is_manager'):
        set_clauses.append("p.is_manager = $is_manager")
    
    # Email can be NULL (for users without email) - UNIQUE constraint allows multiple NULLs
    if _has_value(props, 'email'):
        set_clauses.append("p.email = $email")
    
    # Only set hire_date if not empty
    if _has_value(props, 'hire_date'):
        set_clauses.append("p.hire_date = date($hire_date)")
    if _has_value(props, 'url'):
        set_clauses.append("p.url = $url")
    
    if set_clauses:
        query = f"""
        MERGE (p:Person {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN p
        """
    else:
        query = """
        MERGE (p:Person {id: $id})
        RETURN p
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_team(session: Session, team: Team, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Team node into Neo4j.
    
    This function updates existing Team nodes (including stubs created from Jira references)
    with complete GitHub data. Stub teams created with source='jira_reference' will be
    enriched with full properties when GitHub data loads.
    
    Args:
        session: Neo4j session
        team: Team dataclass instance
        relationships: Optional list of relationships to create
    """
    props = team.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'name'):
        set_clauses.append("t.name = $name")
    if _has_value(props, 'target_size'):
        set_clauses.append("t.target_size = $target_size")
    # Mark as enriched by GitHub (overwrites 'jira_reference' if it was a stub)
    set_clauses.append("t.source = 'github'")
    
    # Only set created_at if it's not empty
    if _has_value(props, 'created_at'):
        set_clauses.append("t.created_at = date($created_at)")
    if _has_value(props, 'url'):
        set_clauses.append("t.url = $url")
    
    # MERGE the Team node
    if set_clauses:
        query = f"""
        MERGE (t:Team {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN t
        """
    else:
        query = """
        MERGE (t:Team {id: $id})
        RETURN t
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_identity_mapping(session: Session, identity: IdentityMapping, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge an IdentityMapping node into Neo4j.
    
    Args:
        session: Neo4j session
        identity: IdentityMapping dataclass instance
        relationships: Optional list of relationships to create
    """
    props = identity.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'provider'):
        set_clauses.append("i.provider = $provider")
    if _has_value(props, 'username'):
        set_clauses.append("i.username = $username")
    if _has_value(props, 'email'):
        set_clauses.append("i.email = $email")
    
    # Only set last_updated_at if provided
    if _has_value(props, 'last_updated_at'):
        set_clauses.append("i.last_updated_at = datetime($last_updated_at)")
    
    # MERGE the IdentityMapping node
    if set_clauses:
        query = f"""
        MERGE (i:IdentityMapping {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN i
        """
    else:
        query = """
        MERGE (i:IdentityMapping {id: $id})
        RETURN i
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


# ============================================================================
# LAYER 2 MERGE FUNCTIONS
# ============================================================================

def merge_project(session: Session, project: Project, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Project node into Neo4j.
    
    Args:
        session: Neo4j session
        project: Project dataclass instance
        relationships: Optional list of relationships to create
    """
    props = project.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'key'):
        set_clauses.append("p.key = $key")
    if _has_value(props, 'name'):
        set_clauses.append("p.name = $name")
    if _has_value(props, 'status'):
        set_clauses.append("p.status = $status")
    if _has_value(props, 'project_type'):
        set_clauses.append("p.project_type = $project_type")
    if _has_value(props, 'url'):
        set_clauses.append("p.url = $url")
    
    # MERGE the Project node
    if set_clauses:
        query = f"""
        MERGE (p:Project {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN p
        """
    else:
        query = """
        MERGE (p:Project {id: $id})
        RETURN p
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_initiative(session: Session, initiative: Initiative, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge an Initiative node into Neo4j.
    
    Args:
        session: Neo4j session
        initiative: Initiative dataclass instance (extends JiraIssueBase)
        relationships: Optional list of relationships to create
    """
    props = initiative.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'key'):
        set_clauses.append("i.key = $key")
    if _has_value(props, 'summary'):
        set_clauses.append("i.summary = $summary")
    if _has_value(props, 'priority'):
        set_clauses.append("i.priority = $priority")
    if _has_value(props, 'status'):
        set_clauses.append("i.status = $status")
    
    # Only set date fields if they are not empty strings
    if _has_value(props, 'created_at'):
        set_clauses.append("i.created_at = date($created_at)")
    if _has_value(props, 'updated_at'):
        set_clauses.append("i.updated_at = date($updated_at)")
    if _has_value(props, 'duedate'):
        set_clauses.append("i.duedate = date($duedate)")
    if _has_value(props, 'labels'):
        set_clauses.append("i.labels = $labels")
    if _has_value(props, 'components'):
        set_clauses.append("i.components = $components")
    if _has_value(props, 'project_id'):
        set_clauses.append("i.project_id = $project_id")
    if _has_value(props, 'url'):
        set_clauses.append("i.url = $url")
    # Only set _last_synced_at if provided (for incremental sync tracking)
    if _has_value(props, '_last_synced_at'):
        set_clauses.append("i._last_synced_at = datetime($_last_synced_at)")
    
    # MERGE the Initiative node
    if set_clauses:
        query = f"""
        MERGE (i:Initiative {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN i
        """
    else:
        query = """
        MERGE (i:Initiative {id: $id})
        RETURN i
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_epic(session: Session, epic: Epic, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge an Epic node into Neo4j.
    
    Args:
        session: Neo4j session
        epic: Epic dataclass instance
        relationships: Optional list of relationships to create
    """
    props = epic.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'key'):
        set_clauses.append("e.key = $key")
    if _has_value(props, 'summary'):
        set_clauses.append("e.summary = $summary")
    if _has_value(props, 'priority'):
        set_clauses.append("e.priority = $priority")
    if _has_value(props, 'status'):
        set_clauses.append("e.status = $status")
    
    # Only set date fields if they are not empty strings
    if _has_value(props, 'start_date'):
        set_clauses.append("e.start_date = date($start_date)")
    if _has_value(props, 'due_date'):
        set_clauses.append("e.due_date = date($due_date)")
    if _has_value(props, 'created_at'):
        set_clauses.append("e.created_at = date($created_at)")
    if _has_value(props, 'updated_at'):
        set_clauses.append("e.updated_at = date($updated_at)")
    if _has_value(props, 'url'):
        set_clauses.append("e.url = $url")
    # Only set _last_synced_at if provided (for incremental sync tracking)
    if _has_value(props, '_last_synced_at'):
        set_clauses.append("e._last_synced_at = datetime($_last_synced_at)")
    
    # MERGE the Epic node
    if set_clauses:
        query = f"""
        MERGE (e:Epic {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN e
        """
    else:
        query = """
        MERGE (e:Epic {id: $id})
        RETURN e
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_issue(session: Session, issue: Issue, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge an Issue node into Neo4j.
    
    This function updates existing Issue nodes (including stubs created from GitHub references)
    with complete Jira data. Stub issues created with source='github_reference' will be
    enriched with full properties when Jira data loads.
    
    Args:
        session: Neo4j session
        issue: Issue dataclass instance
        relationships: Optional list of relationships to create
    """
    props = issue.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'key'):
        set_clauses.append("i.key = $key")
    if _has_value(props, 'type'):
        set_clauses.append("i.type = $type")
    if _has_value(props, 'summary'):
        set_clauses.append("i.summary = $summary")
    if _has_value(props, 'priority'):
        set_clauses.append("i.priority = $priority")
    if _has_value(props, 'status'):
        set_clauses.append("i.status = $status")
    if _has_value(props, 'story_points'):
        set_clauses.append("i.story_points = $story_points")
    # Mark as enriched by Jira (overwrites 'github_reference' if it was a stub)
    set_clauses.append("i.source = 'jira'")
    
    # Only set created_at/updated_at if it's not empty
    if _has_value(props, 'created_at'):
        set_clauses.append("i.created_at = datetime($created_at)")
    if _has_value(props, 'updated_at'):
        set_clauses.append("i.updated_at = datetime($updated_at)")
    if _has_value(props, 'url'):
        set_clauses.append("i.url = $url")
    # Only set _last_synced_at if provided (for incremental sync tracking)
    if _has_value(props, '_last_synced_at'):
        set_clauses.append("i._last_synced_at = datetime($_last_synced_at)")
    
    # MERGE the Issue node
    if set_clauses:
        query = f"""
        MERGE (i:Issue {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN i
        """
    else:
        query = """
        MERGE (i:Issue {id: $id})
        RETURN i
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_sprint(session: Session, sprint: Sprint, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Sprint node into Neo4j.
    
    Args:
        session: Neo4j session
        sprint: Sprint dataclass instance
        relationships: Optional list of relationships to create
    """
    props = sprint.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'name'):
        set_clauses.append("s.name = $name")
    if _has_value(props, 'goal'):
        set_clauses.append("s.goal = $goal")
    if _has_value(props, 'status'):
        set_clauses.append("s.status = $status")
    
    # Only set date fields if they are not empty strings
    if _has_value(props, 'start_date'):
        set_clauses.append("s.start_date = date($start_date)")
    if _has_value(props, 'end_date'):
        set_clauses.append("s.end_date = date($end_date)")
    if _has_value(props, 'url'):
        set_clauses.append("s.url = $url")
    
    # MERGE the Sprint node
    if set_clauses:
        query = f"""
        MERGE (s:Sprint {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN s
        """
    else:
        query = """
        MERGE (s:Sprint {id: $id})
        RETURN s
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


# ============================================================================
# LAYER 5 MERGE FUNCTIONS
# ============================================================================

def merge_repository(session: Session, repository: Repository, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Repository node into Neo4j.
    
    Args:
        session: Neo4j session
        repository: Repository dataclass instance
        relationships: Optional list of relationships to create
    """
    props = repository.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'name'):
        set_clauses.append("r.name = $name")
    if _has_value(props, 'full_name'):
        set_clauses.append("r.full_name = $full_name")
    if _has_value(props, 'created_at'):
        set_clauses.append("r.created_at = date($created_at)")
    if _has_value(props, 'url'):
        set_clauses.append("r.url = $url")
    if _has_value(props, 'language'):
        set_clauses.append("r.language = $language")
    if _has_value(props, 'is_private'):
        set_clauses.append("r.is_private = $is_private")
    if _has_value(props, 'topics'):
        set_clauses.append("r.topics = $topics")
    
    # Only set _last_synced_at if provided (for incremental sync tracking)
    if _has_value(props, '_last_synced_at'):
        set_clauses.append("r._last_synced_at = datetime($_last_synced_at)")
    
    # MERGE the Repository node
    if set_clauses:
        query = f"""
        MERGE (r:Repository {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN r
        """
    else:
        query = """
        MERGE (r:Repository {id: $id})
        RETURN r
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


# ============================================================================
# LAYER 6 MERGE FUNCTIONS
# ============================================================================

def merge_branch(session: Session, branch: Branch, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Branch node into Neo4j.
    
    Args:
        session: Neo4j session
        branch: Branch dataclass instance
        relationships: Optional list of relationships to create
    """
    props = branch.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'name'):
        set_clauses.append("b.name = $name")
    if _has_value(props, 'is_default'):
        set_clauses.append("b.is_default = $is_default")
    if _has_value(props, 'is_protected'):
        set_clauses.append("b.is_protected = $is_protected")
    if _has_value(props, 'is_external'):
        set_clauses.append("b.is_external = $is_external")
    if _has_value(props, 'last_commit_sha'):
        set_clauses.append("b.last_commit_sha = $last_commit_sha")
    if _has_value(props, 'last_commit_timestamp'):
        set_clauses.append("b.last_commit_timestamp = datetime($last_commit_timestamp)")
    if _has_value(props, 'is_deleted'):
        set_clauses.append("b.is_deleted = $is_deleted")
    if _has_value(props, 'url'):
        set_clauses.append("b.url = $url")
    
    # MERGE the Branch node
    if set_clauses:
        query = f"""
        MERGE (b:Branch {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN b
        """
    else:
        query = """
        MERGE (b:Branch {id: $id})
        RETURN b
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


# ============================================================================
# LAYER 7 MERGE FUNCTIONS
# ============================================================================

def merge_commit(session: Session, commit: Commit, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a Commit node into Neo4j.
    
    Args:
        session: Neo4j session
        commit: Commit dataclass instance
        relationships: Optional list of relationships to create
    """
    props = commit.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'sha'):
        set_clauses.append("c.sha = $sha")
    if _has_value(props, 'message'):
        set_clauses.append("c.message = $message")
    if _has_value(props, 'created_at'):
        set_clauses.append("c.created_at = datetime($created_at)")
    if _has_value(props, 'additions'):
        set_clauses.append("c.additions = $additions")
    if _has_value(props, 'deletions'):
        set_clauses.append("c.deletions = $deletions")
    if _has_value(props, 'files_changed'):
        set_clauses.append("c.files_changed = $files_changed")
    
    if _has_value(props, 'url'):
        set_clauses.append("c.url = $url")
    
    # MERGE the Commit node
    if set_clauses:
        query = f"""
        MERGE (c:Commit {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN c
        """
    else:
        query = """
        MERGE (c:Commit {id: $id})
        RETURN c
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


def merge_file(session: Session, file: File, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a File node into Neo4j.
    
    Args:
        session: Neo4j session
        file: File dataclass instance
        relationships: Optional list of relationships to create
    """
    props = file.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'path'):
        set_clauses.append("f.path = $path")
    if _has_value(props, 'name'):
        set_clauses.append("f.name = $name")
    if _has_value(props, 'extension'):
        set_clauses.append("f.extension = $extension")
    if _has_value(props, 'language'):
        set_clauses.append("f.language = $language")
    if _has_value(props, 'is_test'):
        set_clauses.append("f.is_test = $is_test")
    if _has_value(props, 'size'):
        set_clauses.append("f.size = $size")
    if _has_value(props, 'created_at'):
        set_clauses.append("f.created_at = datetime($created_at)")
    if _has_value(props, 'url'):
        set_clauses.append("f.url = $url")
    
    # MERGE the File node
    if set_clauses:
        query = f"""
        MERGE (f:File {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN f
        """
    else:
        query = """
        MERGE (f:File {id: $id})
        RETURN f
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


# ============================================================================
# LAYER 8 MERGE FUNCTIONS
# ============================================================================

def merge_pull_request(session: Session, pull_request: PullRequest, relationships: Optional[List[Relationship]] = None) -> None:
    """
    Merge a PullRequest node into Neo4j.
    
    Args:
        session: Neo4j session
        pull_request: PullRequest dataclass instance
        relationships: Optional list of relationships to create
    """
    props = pull_request.to_neo4j_properties()
    
    # Build SET clause dynamically based on available properties (additive updates only)
    set_clauses = []
    if _has_value(props, 'number'):
        set_clauses.append("pr.number = $number")
    if _has_value(props, 'created_at'):
        set_clauses.append("pr.created_at = datetime($created_at)")
    if _has_value(props, 'title'):
        set_clauses.append("pr.title = $title")
    if _has_value(props, 'state'):
        set_clauses.append("pr.state = $state")
    if _has_value(props, 'updated_at'):
        set_clauses.append("pr.updated_at = datetime($updated_at)")
    if _has_value(props, 'merged_at'):
        set_clauses.append("pr.merged_at = datetime($merged_at)")
    if _has_value(props, 'closed_at'):
        set_clauses.append("pr.closed_at = datetime($closed_at)")
    if _has_value(props, 'commits_count'):
        set_clauses.append("pr.commits_count = $commits_count")
    if _has_value(props, 'additions'):
        set_clauses.append("pr.additions = $additions")
    if _has_value(props, 'deletions'):
        set_clauses.append("pr.deletions = $deletions")
    if _has_value(props, 'changed_files'):
        set_clauses.append("pr.changed_files = $changed_files")
    if _has_value(props, 'comments'):
        set_clauses.append("pr.comments = $comments")
    if _has_value(props, 'review_comments'):
        set_clauses.append("pr.review_comments = $review_comments")
    if _has_value(props, 'head_branch_name'):
        set_clauses.append("pr.head_branch_name = $head_branch_name")
    if _has_value(props, 'base_branch_name'):
        set_clauses.append("pr.base_branch_name = $base_branch_name")
    if _has_value(props, 'labels'):
        set_clauses.append("pr.labels = $labels")
    if _has_value(props, 'mergeable_state'):
        set_clauses.append("pr.mergeable_state = $mergeable_state")
    if _has_value(props, 'url'):
        set_clauses.append("pr.url = $url")
    
    # MERGE the PullRequest node
    if set_clauses:
        query = f"""
        MERGE (pr:PullRequest {{id: $id}})
        SET {', '.join(set_clauses)}
        RETURN pr
        """
    else:
        query = """
        MERGE (pr:PullRequest {id: $id})
        RETURN pr
        """
    
    session.run(query, **props)
    
    # Create relationships if provided
    if relationships:
        for rel in relationships:
            merge_relationship(session, rel)


# ============================================================================
# GENERIC RELATIONSHIP MERGE
# ============================================================================

def merge_relationship(session: Session, relationship: Relationship) -> None:
    """
    Merge a relationship between two nodes, creating nodes if they don't exist.
    Automatically creates reverse edges for directional relationship pairs.
    
    Args:
        session: Neo4j session
        relationship: Relationship dataclass instance
    """
    rel_type = relationship.type
    from_id = relationship.from_id
    to_id = relationship.to_id
    from_type = relationship.from_type
    to_type = relationship.to_type
    props = relationship.properties
    
    # Build property string for Cypher
    props_str = ""
    if props:
        props_items = [f"{k}: ${k}" for k in props.keys()]
        props_str = "{" + ", ".join(props_items) + "}"
    
    # Create the forward relationship
    forward_query = f"""
    MERGE (from:{from_type} {{id: $from_id}})
    MERGE (to:{to_type} {{id: $to_id}})
    MERGE (from)-[r:{rel_type} {props_str}]->(to)
    RETURN r
    """
    
    params = {
        "from_id": from_id,
        "to_id": to_id,
        **props
    }
    
    session.run(forward_query, **params)
    
    # Create the reverse relationship for directional pairs only
    if rel_type in DIRECTIONAL_RELATIONSHIPS:
        reverse_type = DIRECTIONAL_RELATIONSHIPS[rel_type]
        reverse_query = f"""
        MERGE (from:{to_type} {{id: $to_id}})
        MERGE (to:{from_type} {{id: $from_id}})
        MERGE (from)-[r:{reverse_type} {props_str}]->(to)
        RETURN r
        """
        
        session.run(reverse_query, **params)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
