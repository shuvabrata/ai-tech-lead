"""
Query executor with metrics collection.
"""

import time
from typing import List, Dict, Any
from neo4j import Session
from neo4j.time import DateTime, Date, Time, Duration

from .models import QueryResult, QueryExpectation


class QueryExecutor:
    """Executes Neo4j queries and captures metrics."""
    
    def __init__(self, session: Session):
        """Initialize with Neo4j session."""
        self.session = session
    
    def execute(
        self,
        query_name: str,
        section: str,
        query_text: str,
        expectation: QueryExpectation = None,
        parameters: Dict[str, Any] = None
    ) -> QueryResult:
        """
        Execute a query and capture all metrics.
        
        Args:
            query_name: Human-readable name for the query
            section: Section/category (e.g., "People & Identity")
            query_text: Cypher query to execute
            expectation: Optional expectations for validation
            parameters: Optional dictionary of Cypher parameters
            
        Returns:
            QueryResult with all metrics and status
        """
        # Add LIMIT 10 to queries that don't already have LIMIT
        limited_query = self._add_limit_if_missing(query_text, limit=10)
        
        result = QueryResult(
            query_name=query_name,
            section=section,
            query_text=query_text,  # Store original query
            expectation=expectation
        )
        
        start = time.perf_counter()
        
        try:
            # Execute query with LIMIT
            records = list(self.session.run(limited_query, **(parameters or {})))
            result.execution_time_ms = (time.perf_counter() - start) * 1000
            result.row_count = len(records)
            
            # Capture result rows (already limited to 10) with type conversion
            result.result_rows = [self._convert_record_to_dict(record) for record in records]
            
            # Tier 1: Query executed successfully = PASS (schema is valid)
            result.status = "PASS"
            
            # Check for empty columns if we have data
            if records:
                result.empty_columns = self._check_empty_columns(records)
            
            # Tier 2: Apply expectations if provided
            if expectation:
                self._apply_expectations(result, records, expectation)
            else:
                # Default concerns without explicit expectations
                if result.row_count == 0:
                    result.status = "WARNING"
                    result.details = "No data returned"
                elif result.execution_time_ms > 1000:  # Default threshold
                    result.status = "CONCERN"
                    result.details = f"Slow query: {result.execution_time_ms:.0f}ms"
                elif result.empty_columns:
                    result.status = "CONCERN"
                    result.details = f"Empty columns: {', '.join(result.empty_columns)}"
            
        except Exception as e:
            result.execution_time_ms = (time.perf_counter() - start) * 1000
            result.has_error = True
            result.error_message = str(e)
            result.status = "FAIL"
            result.details = f"Query execution error: {str(e)}"
        
        return result
    
    def _add_limit_if_missing(self, query: str, limit: int = 10) -> str:
        """Add LIMIT clause to query if not already present."""
        query_upper = query.upper()
        if 'LIMIT' not in query_upper:
            # Add LIMIT before any trailing semicolon
            query = query.rstrip().rstrip(';')
            return f"{query}\nLIMIT {limit}"
        return query
    
    def _convert_record_to_dict(self, record) -> Dict[str, Any]:
        """Convert a Neo4j record to a JSON-serializable dictionary."""
        result = {}
        for key, value in record.items():
            # Convert Neo4j temporal types to ISO strings
            if isinstance(value, DateTime):
                result[key] = value.iso_format()
            elif isinstance(value, Date):
                result[key] = value.iso_format()
            elif isinstance(value, Time):
                result[key] = value.iso_format()
            elif isinstance(value, Duration):
                result[key] = str(value)
            elif isinstance(value, list):
                # Recursively convert lists
                result[key] = [self._convert_value(item) for item in value]
            elif isinstance(value, dict):
                # Recursively convert dicts
                result[key] = {k: self._convert_value(v) for k, v in value.items()}
            else:
                result[key] = value
        return result
    
    def _convert_value(self, value: Any) -> Any:
        """Convert a single value to JSON-serializable format."""
        if isinstance(value, (DateTime, Date, Time)):
            return value.iso_format()
        elif isinstance(value, Duration):
            return str(value)
        elif isinstance(value, list):
            return [self._convert_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._convert_value(v) for k, v in value.items()}
        else:
            return value
    
    def _check_empty_columns(self, records: List[Dict[str, Any]]) -> List[str]:
        """Identify columns that have all NULL/None values."""
        if not records:
            return []
        
        # Get all column names from first record
        columns = list(records[0].keys())
        empty_columns = []
        
        for col in columns:
            # Check if all values in this column are None/NULL
            if all(record[col] is None for record in records):
                empty_columns.append(col)
        
        return empty_columns
    
    def _apply_expectations(
        self,
        result: QueryResult,
        records: List[Dict[str, Any]],
        expectation: QueryExpectation
    ) -> None:
        """Apply expectations and update result status."""
        concerns = []
        
        # Check row count expectations
        if expectation.min_rows is not None and result.row_count < expectation.min_rows:
            result.status = "CONCERN"
            concerns.append(f"Expected min {expectation.min_rows} rows, got {result.row_count}")
        
        if expectation.max_rows is not None and result.row_count > expectation.max_rows:
            result.status = "CONCERN"
            concerns.append(f"Expected max {expectation.max_rows} rows, got {result.row_count}")
        
        # Check execution time
        if expectation.max_time_ms is not None and result.execution_time_ms > expectation.max_time_ms:
            result.status = "CONCERN"
            concerns.append(f"Slow query: {result.execution_time_ms:.0f}ms (max: {expectation.max_time_ms}ms)")
        
        # Check required columns
        if expectation.required_columns and records:
            actual_columns = set(records[0].keys())
            missing_columns = set(expectation.required_columns) - actual_columns
            if missing_columns:
                result.status = "CONCERN"
                concerns.append(f"Missing required columns: {', '.join(missing_columns)}")
        
        # Check empty columns
        if not expectation.allow_empty_columns and result.empty_columns:
            result.status = "CONCERN"
            concerns.append(f"Empty columns not allowed: {', '.join(result.empty_columns)}")
        
        # Update details with all concerns
        if concerns:
            result.details = "; ".join(concerns)
        elif result.row_count == 0 and expectation.min_rows == 0:
            # Explicitly expected to return 0 rows - still PASS
            result.details = "No data (as expected)"
        elif result.status == "PASS":
            result.details = "All expectations met"
