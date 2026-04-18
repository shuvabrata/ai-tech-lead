"""Backend-owned registry for server-filterable graph properties.

This registry is the source of truth for which node/relationship properties
can be safely used by the server-side filter endpoint.
"""

from typing import Any, Dict, List


FILTER_REGISTRY: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {
    "nodes": {
        "Person": {
            "name": {"type": "string", "operators": ["=", "CONTAINS", "STARTS WITH"], "server": True, "indexed": True},
            "email": {"type": "string", "operators": ["=", "CONTAINS"], "server": True, "indexed": True},
            "role": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
            "title": {"type": "string", "operators": ["=", "CONTAINS", "STARTS WITH"], "server": True, "indexed": True},
        },
        "File": {
            "path": {"type": "string", "operators": ["=", "CONTAINS", "STARTS WITH"], "server": True, "indexed": True},
            "extension": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
            "language": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
            "is_test": {"type": "boolean", "operators": ["="], "server": True, "indexed": True},
        },
        "PullRequest": {
            "state": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
            "created_at": {"type": "date", "operators": [">=", "<=", "="], "server": True, "indexed": True},
            "merged_at": {"type": "date", "operators": [">=", "<=", "="], "server": True, "indexed": True},
        },
        "Issue": {
            "status": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
            "type": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
            "created_at": {"type": "date", "operators": [">=", "<=", "="], "server": True, "indexed": True},
        },
        "Branch": {
            "name": {"type": "string", "operators": ["=", "CONTAINS", "STARTS WITH"], "server": True, "indexed": True},
            "is_default": {"type": "boolean", "operators": ["="], "server": True, "indexed": True},
            "is_protected": {"type": "boolean", "operators": ["="], "server": True, "indexed": True},
        },
    },
    "relationships": {
        "REVIEWED_BY": {
            "state": {"type": "string", "operators": ["="], "server": True}
        }
    },
}


def get_node_property_config(label: str, property_name: str) -> Dict[str, Any] | None:
    """Return registry config for a node property, if supported."""
    return FILTER_REGISTRY.get("nodes", {}).get(label, {}).get(property_name)


def get_relationship_property_config(rel_type: str, property_name: str) -> Dict[str, Any] | None:
    """Return registry config for a relationship property, if supported."""
    return FILTER_REGISTRY.get("relationships", {}).get(rel_type, {}).get(property_name)


def get_supported_node_labels() -> List[str]:
    """Return all node labels present in the registry."""
    return list(FILTER_REGISTRY.get("nodes", {}).keys())


def get_supported_relationship_types() -> List[str]:
    """Return all relationship types present in the registry."""
    return list(FILTER_REGISTRY.get("relationships", {}).keys())
