"""
Import and analyze relationship definitions from codebase.
"""

import sys
from pathlib import Path
from typing import Dict, Set, Tuple, Optional

# Add project root to path to import db.models
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from neo4j_db.models import DIRECTIONAL_RELATIONSHIPS, UNDIRECTED_RELATIONSHIPS


def get_expected_relationships() -> Dict[str, str]:
    """
    Get expected directional relationships from DIRECTIONAL_RELATIONSHIPS in db/models.py.
    
    Returns:
        Dictionary mapping relationship type to its reverse type.
    """
    return dict(DIRECTIONAL_RELATIONSHIPS)


def get_all_relationship_names() -> Set[str]:
    """
    Get all unique relationship names (directional forward/reverse + undirected).
    
    Returns:
        Set of all unique relationship type names
    """
    all_names = set()
    for forward, reverse in DIRECTIONAL_RELATIONSHIPS.items():
        all_names.add(forward)
        if reverse:
            all_names.add(reverse)
    for name in UNDIRECTED_RELATIONSHIPS:
        all_names.add(name)
    return all_names


def categorize_relationships() -> Tuple[Set[str], Dict[str, Set[str]], Set[str]]:
    """
    Categorize relationships by type.
    
    Returns:
        Tuple of (undirected, different_name_bidirectional, unidirectional)
        - undirected: Set of relationship names stored as single edges and queried undirected
        - different_name_bidirectional: Dict mapping forward->reverse for directional pairs
        - unidirectional: Set of relationships that only go one way
    """
    undirected = set(UNDIRECTED_RELATIONSHIPS)
    different_name = {}
    unidirectional = set()
    
    processed = set()
    
    for forward, reverse in DIRECTIONAL_RELATIONSHIPS.items():
        if forward in processed:
            continue
        
        if reverse and reverse in DIRECTIONAL_RELATIONSHIPS:
            # Different name bidirectional (both directions exist in dict)
            different_name[forward] = reverse
            processed.add(forward)
            processed.add(reverse)
        else:
            # Could be unidirectional or incomplete definition
            # For now, treat as different-name if reverse exists
            if reverse:
                different_name[forward] = reverse
                processed.add(forward)
    
    return undirected, different_name, unidirectional


def get_relationship_pair(rel_type: str) -> Optional[str]:
    """
    Get the paired relationship type for a directional relationship.
    
    Args:
        rel_type: Relationship type name
        
    Returns:
        The reverse relationship type, or None if unidirectional or undirected
    """
    if rel_type in DIRECTIONAL_RELATIONSHIPS:
        reverse = DIRECTIONAL_RELATIONSHIPS[rel_type]
        return reverse
    
    # Check if this is a reverse relationship
    for forward, reverse in DIRECTIONAL_RELATIONSHIPS.items():
        if reverse == rel_type and forward != reverse:
            return forward
    
    return None


def is_bidirectional(rel_type: str) -> bool:
    """
    Check if a relationship type is directional (requires reverse edge).
    
    Args:
        rel_type: Relationship type name
        
    Returns:
        True if relationship is directional (has explicit reverse edge)
    """
    if rel_type in DIRECTIONAL_RELATIONSHIPS:
        return True
    
    # Check if it's a reverse relationship
    for forward, reverse in DIRECTIONAL_RELATIONSHIPS.items():
        if reverse == rel_type:
            return True
    
    return False


def is_same_name_bidirectional(rel_type: str) -> bool:
    """
    Check if a relationship is stored as undirected.
    
    Args:
        rel_type: Relationship type name
        
    Returns:
        True if relationship is undirected
    """
    return rel_type in UNDIRECTED_RELATIONSHIPS


def print_relationship_summary():
    """Print summary of expected relationships."""
    undirected, different_name, unidirectional = categorize_relationships()
    all_names = get_all_relationship_names()
    
    print(f"\n{'='*80}")
    print(f"EXPECTED RELATIONSHIPS FROM db/models.py")
    print(f"{'='*80}\n")
    
    print(f"Undirected ({len(undirected)}):")
    for name in sorted(undirected):
        print(f"  - {name} (stored once)")
    
    print(f"\nDifferent-name bidirectional ({len(different_name)} pairs):")
    processed = set()
    for forward, reverse in sorted(different_name.items()):
        if forward not in processed and reverse not in processed:
            print(f"  - {forward} ↔ {reverse}")
            processed.add(forward)
            processed.add(reverse)
    
    if unidirectional:
        print(f"\nUnidirectional ({len(unidirectional)}):")
        for name in sorted(unidirectional):
            print(f"  - {name} →")
    
    print(f"\nTotal unique relationship names: {len(all_names)}")


if __name__ == "__main__":
    print_relationship_summary()
