from typing import Dict

def map_permissions_to_general(permissions: Dict[str, bool]) -> str:
    """
    Map GitHub permissions to general READ or WRITE access.

    Args:
        permissions: Dictionary of permission flags (with underscore prefixes)

    Returns:
        str: "WRITE" or "READ" based on permissions
    """
    # WRITE permissions (in order of precedence)
    write_permissions = ['_admin', '_maintain', '_push']

    # Check if user has any write permissions
    for perm in write_permissions:
        if permissions.get(perm, False):
            return "WRITE"

    # Default to READ (includes '_pull', '_triage', or any read-only access)
    return "READ"