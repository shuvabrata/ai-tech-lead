"""
Data models for property validation results.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class PopulationCategory(Enum):
    """Category for property population status."""
    FULL = "FULL"          # 100% populated
    PARTIAL = "PARTIAL"    # 1-99% populated
    EMPTY = "EMPTY"        # 0% populated


@dataclass
class PropertyMetadata:
    """Metadata about a property from the dataclass definition."""
    name: str
    python_type: str
    is_optional: bool


@dataclass
class EntityMetadata:
    """Metadata about an entity type discovered from models.py."""
    entity_name: str
    properties: List[PropertyMetadata]


@dataclass
class PropertyValidationResult:
    """Validation result for a single property."""
    property_name: str
    entity_or_rel_type: str
    total_count: int
    populated_count: int
    empty_count: int
    population_percentage: float
    category: PopulationCategory
    is_required: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'property_name': self.property_name,
            'entity_or_rel_type': self.entity_or_rel_type,
            'total_count': self.total_count,
            'populated_count': self.populated_count,
            'empty_count': self.empty_count,
            'population_percentage': self.population_percentage,
            'category': self.category.value,
            'is_required': self.is_required
        }


@dataclass
class RelationshipExistenceResult:
    """Validation result for relationship existence and consistency."""
    rel_type: str
    total_count: int
    has_properties: bool
    is_expected: bool  # Is this relationship defined in model relationship definitions?
    is_bidirectional: bool
    is_same_name_bidirectional: bool
    reverse_rel_type: Optional[str] = None
    reverse_count: Optional[int] = None
    count_discrepancy: Optional[int] = None  # Difference between forward and reverse counts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'rel_type': self.rel_type,
            'total_count': self.total_count,
            'has_properties': self.has_properties,
            'is_expected': self.is_expected,
            'is_bidirectional': self.is_bidirectional,
            'is_same_name_bidirectional': self.is_same_name_bidirectional,
            'reverse_rel_type': self.reverse_rel_type,
            'reverse_count': self.reverse_count,
            'count_discrepancy': self.count_discrepancy
        }


@dataclass
class RelationshipCoverageResult:
    """Summary of relationship coverage against expected definitions."""
    expected_count: int
    discovered_count: int
    missing_relationships: List[str] = field(default_factory=list)
    unexpected_relationships: List[str] = field(default_factory=list)
    bidirectional_mismatches: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'expected_count': self.expected_count,
            'discovered_count': self.discovered_count,
            'missing_relationships': self.missing_relationships,
            'unexpected_relationships': self.unexpected_relationships,
            'bidirectional_mismatches': self.bidirectional_mismatches,
            'coverage_percentage': (self.discovered_count / self.expected_count * 100) if self.expected_count > 0 else 0.0
        }


@dataclass
class ValidationReport:
    """Complete validation report for all entities and relationships."""
    timestamp: datetime
    entity_results: Dict[str, List[PropertyValidationResult]]
    relationship_results: Dict[str, List[PropertyValidationResult]]
    relationship_existence: Dict[str, RelationshipExistenceResult] = field(default_factory=dict)
    relationship_coverage: Optional[RelationshipCoverageResult] = None
    failure_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'entity_results': {
                entity_type: [result.to_dict() for result in results]
                for entity_type, results in self.entity_results.items()
            },
            'relationship_results': {
                rel_type: [result.to_dict() for result in results]
                for rel_type, results in self.relationship_results.items()
            },
            'relationship_existence': {
                rel_type: result.to_dict()
                for rel_type, result in self.relationship_existence.items()
            },
            'relationship_coverage': self.relationship_coverage.to_dict() if self.relationship_coverage else None,
            'failure_count': self.failure_count,
            'summary': self._generate_summary()
        }
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        total_properties = sum(len(results) for results in self.entity_results.values())
        total_rel_properties = sum(len(results) for results in self.relationship_results.values())
        
        full_count = 0
        partial_count = 0
        empty_count = 0
        
        for results in self.entity_results.values():
            for result in results:
                if result.category == PopulationCategory.FULL:
                    full_count += 1
                elif result.category == PopulationCategory.PARTIAL:
                    partial_count += 1
                else:
                    empty_count += 1
        
        for results in self.relationship_results.values():
            for result in results:
                if result.category == PopulationCategory.FULL:
                    full_count += 1
                elif result.category == PopulationCategory.PARTIAL:
                    partial_count += 1
                else:
                    empty_count += 1
        
        summary = {
            'total_entity_types': len(self.entity_results),
            'total_relationship_types': len(self.relationship_results),
            'total_relationship_existence_checks': len(self.relationship_existence),
            'total_properties_validated': total_properties + total_rel_properties,
            'full_population': full_count,
            'partial_population': partial_count,
            'empty_population': empty_count,
            'failures': self.failure_count
        }
        
        # Add coverage summary if available
        if self.relationship_coverage:
            summary['relationship_coverage'] = {
                'expected': self.relationship_coverage.expected_count,
                'discovered': self.relationship_coverage.discovered_count,
                'missing': len(self.relationship_coverage.missing_relationships),
                'unexpected': len(self.relationship_coverage.unexpected_relationships),
                'coverage_percentage': (self.relationship_coverage.discovered_count / self.relationship_coverage.expected_count * 100) if self.relationship_coverage.expected_count > 0 else 0.0
            }
        
        return summary
