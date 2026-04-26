"""
Dynamically introspect db/models.py to discover entity types and properties.
"""

import sys
import inspect
from dataclasses import fields, is_dataclass
from typing import Dict, get_origin, get_args, Any
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.property_validation.models import EntityMetadata, PropertyMetadata


def is_optional_field(field_type: Any) -> bool:
    """
    Check if a field is Optional (i.e., Union[T, None]).
    
    Args:
        field_type: The type annotation of the field
        
    Returns:
        True if the field is Optional, False otherwise
    """
    origin = get_origin(field_type)
    if origin is None:
        return False
    
    # Check if it's a Union type
    if hasattr(origin, '__name__') and origin.__name__ == 'Union':
        args = get_args(field_type)
        # Optional[T] is actually Union[T, None]
        return type(None) in args
    
    return False


def extract_properties(entity_class: type) -> list[PropertyMetadata]:
    """
    Extract properties from a dataclass.
    
    Args:
        entity_class: The dataclass to extract properties from
        
    Returns:
        List of PropertyMetadata objects
    """
    if not is_dataclass(entity_class):
        return []
    
    properties = []
    for field_obj in fields(entity_class):
        # Skip internal/metadata fields
        if field_obj.name.startswith('_'):
            continue
        
        # Determine if field is optional
        is_optional = is_optional_field(field_obj.type)
        
        # Get type as string for display
        type_str = str(field_obj.type)
        # Clean up type string for readability
        type_str = type_str.replace('typing.', '').replace('<class ', '').replace('>', '').replace("'", '')
        
        properties.append(PropertyMetadata(
            name=field_obj.name,
            python_type=type_str,
            is_optional=is_optional
        ))
    
    return properties


def discover_entity_types() -> Dict[str, EntityMetadata]:
    """
    Discover all entity types from db/models.py.
    
    Returns:
        Dictionary mapping entity name to EntityMetadata
    """
    import db.models as models
    
    entity_metadata = {}
    
    # Get all classes from the models module
    for name, obj in inspect.getmembers(models, inspect.isclass):
        # Skip if not a dataclass
        if not is_dataclass(obj):
            continue
        
        # Skip helper classes like Relationship (it's not a node type)
        if name == 'Relationship':
            continue
        
        # Skip base classes that are not actual entities
        if name.startswith('_'):
            continue
        
        # Skip JiraIssueBase as it's a base class, not a concrete entity
        if name == 'JiraIssueBase':
            continue
        
        # Extract properties from the dataclass
        properties = extract_properties(obj)
        
        if properties:  # Only include entities with properties
            entity_metadata[name] = EntityMetadata(
                entity_name=name,
                properties=properties
            )
    
    return entity_metadata


def print_discovered_entities(entities: Dict[str, EntityMetadata]) -> None:
    """
    Print discovered entities in a readable format.
    
    Args:
        entities: Dictionary of discovered entities
    """
    print(f"\n{'='*80}")
    print(f"DISCOVERED ENTITIES FROM db/models.py")
    print(f"{'='*80}\n")
    
    for entity_name, metadata in sorted(entities.items()):
        print(f"Entity: {entity_name}")
        print(f"  Properties ({len(metadata.properties)}):")
        for prop in metadata.properties:
            optional_marker = " [OPTIONAL]" if prop.is_optional else " [REQUIRED]"
            print(f"    - {prop.name}: {prop.python_type}{optional_marker}")
        print()


if __name__ == "__main__":
    # Test the discovery function
    entities = discover_entity_types()
    print_discovered_entities(entities)
    print(f"Total entities discovered: {len(entities)}")
