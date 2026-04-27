"""
Data models for query testing framework.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class QueryExpectation:
    """Expectations for a query's behavior."""
    min_rows: Optional[int] = None
    max_rows: Optional[int] = None
    max_time_ms: Optional[float] = None
    required_columns: Optional[List[str]] = None
    allow_empty_columns: bool = True


@dataclass
class QueryResult:
    """Results and metrics from query execution."""
    query_name: str
    section: str
    query_text: str
    execution_time_ms: float = 0.0
    row_count: int = 0
    has_error: bool = False
    error_message: Optional[str] = None
    status: str = "PASS"  # PASS, WARNING, CONCERN, FAIL
    empty_columns: List[str] = field(default_factory=list)
    details: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    expectation: Optional[QueryExpectation] = None
    result_rows: List[Dict[str, Any]] = field(default_factory=list)  # Actual query results (limited to 10)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query_name": self.query_name,
            "section": self.section,
            "query_text": self.query_text,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "row_count": self.row_count,
            "has_error": self.has_error,
            "error_message": self.error_message,
            "status": self.status,
            "empty_columns": self.empty_columns,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "result_rows": self.result_rows,
            "expectation": {
                "min_rows": self.expectation.min_rows,
                "max_rows": self.expectation.max_rows,
                "max_time_ms": self.expectation.max_time_ms,
                "required_columns": self.expectation.required_columns,
            } if self.expectation else None
        }


@dataclass
class TestRunSummary:
    """Summary of entire test run."""
    timestamp: datetime
    total_queries: int
    passed: int = 0
    warnings: int = 0
    concerns: int = 0
    failed: int = 0
    avg_execution_time_ms: float = 0.0
    slowest_queries: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_queries": self.total_queries,
            "passed": self.passed,
            "warnings": self.warnings,
            "concerns": self.concerns,
            "failed": self.failed,
            "avg_execution_time_ms": round(self.avg_execution_time_ms, 2),
            "slowest_queries": self.slowest_queries
        }
