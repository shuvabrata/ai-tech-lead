#!/usr/bin/env python3
"""
Pytest test suite for common/logger.py

Tests different log levels, exception handling, and LogContext usage.
Run from project root: pytest tests/test_logger.py -v -s
  -v: verbose output
  -s: show print statements and log output
"""

import sys
import os
import pytest

# Add project root to path to import common modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.logger import logger, LogContext


@pytest.fixture(scope="session", autouse=True)
def display_test_config():
    """Display test configuration at the start of the test session."""
    print("\n" + "=" * 70)
    print("LOGGER TEST SUITE CONFIGURATION")
    print("=" * 70)
    print(f"LOG_FORMAT: {os.getenv('LOG_FORMAT', 'JSON')}")
    print(f"LOG_LEVEL: {os.getenv('LOG_LEVEL', 'INFO')}")
    print("")
    print("Run with different configurations:")
    print("  LOG_FORMAT=TEXT pytest tests/test_logger.py -v -s")
    print("  LOG_FORMAT=JSON pytest tests/test_logger.py -v -s")
    print("  LOG_LEVEL=DEBUG pytest tests/test_logger.py -v -s")
    print("  LOG_LEVEL=WARNING pytest tests/test_logger.py -v -s")
    print("=" * 70)
    print()


def test_basic_log_levels(caplog):
    """Test all log levels without context."""
    print("=" * 70)
    print("TEST 1: Basic Log Levels (No Context)")
    print("=" * 70)
    
    logger.debug("This is a DEBUG message - detailed diagnostic info")
    logger.info("This is an INFO message - general information")
    logger.warning("This is a WARNING message - something unexpected happened")
    logger.error("This is an ERROR message - something failed")
    logger.critical("This is a CRITICAL message - serious error")
    print()
    
    # Minimal assertion: verify logs were generated
    assert len(caplog.records) > 0, "No logs were captured"
    assert any(record.levelname == "CRITICAL" for record in caplog.records)


def test_logs_with_context(caplog):
    """Test logging with LogContext."""
    print("=" * 70)
    print("TEST 2: Logs with LogContext")
    print("=" * 70)
    
    with LogContext(project_id="proj-123", user_id="alice", request_id="req-abc-456"):
        logger.info("Processing user request")
        logger.debug("Fetching data from database")
        logger.warning("Cache miss - fetching from source")
        logger.info("Request completed successfully")
    print()
    
    # Minimal assertion: verify logs were generated with context
    assert len(caplog.records) > 0, "No logs were captured"
    assert any("Processing user request" in record.message for record in caplog.records)


def test_nested_contexts(caplog):
    """Test nested LogContext usage."""
    print("=" * 70)
    print("TEST 3: Nested LogContext")
    print("=" * 70)
    
    with LogContext(project_id="proj-999"):
        logger.info("Outer context - project level")
        
        with LogContext(user_id="bob", request_id="req-xyz-789"):
            logger.info("Inner context - user and request added")
            logger.debug("Processing nested operation")
        
        logger.info("Back to outer context - only project_id")
    print()
    
    # Minimal assertion: verify nested context logs were generated
    assert len(caplog.records) >= 3, "Expected at least 3 log records"
    assert any("Outer context" in record.message for record in caplog.records)


def test_partial_context(caplog):
    """Test LogContext with only some fields set."""
    print("=" * 70)
    print("TEST 4: Partial LogContext (only request_id)")
    print("=" * 70)
    
    with LogContext(request_id="req-partial-123"):
        logger.info("Only request_id is set in context")
        logger.warning("Other context fields are empty")
    print()
    
    # Minimal assertion: verify logs were generated
    assert len(caplog.records) >= 2, "Expected at least 2 log records"
    assert any(record.levelname == "WARNING" for record in caplog.records)


def test_exception_logging(caplog):
    """Test exception logging with logger.exception()."""
    print("=" * 70)
    print("TEST 5: Exception Logging")
    print("=" * 70)
    
    try:
        result = 10 / 0
    except ZeroDivisionError as e:
        logger.exception("Division by zero error occurred")
    print()
    
    # Minimal assertion: verify exception was logged
    assert len(caplog.records) > 0, "No exception logs were captured"
    assert any(record.levelname == "ERROR" for record in caplog.records)
    assert any(record.exc_info is not None for record in caplog.records)


def test_exception_with_context(caplog):
    """Test exception logging with LogContext."""
    print("=" * 70)
    print("TEST 6: Exception with LogContext")
    print("=" * 70)
    
    with LogContext(project_id="proj-error", user_id="charlie", request_id="req-err-001"):
        try:
            data = {"key": "value"}
            value = data["missing_key"]
        except KeyError as e:
            logger.exception("Failed to access dictionary key")
    print()
    
    # Minimal assertion: verify exception with context was logged
    assert len(caplog.records) > 0, "No exception logs were captured"
    assert any(record.exc_info is not None for record in caplog.records)


def test_error_method_with_exception(caplog):
    """Test logger.error() with exception object."""
    print("=" * 70)
    print("TEST 7: logger.error() with Exception Object")
    print("=" * 70)
    
    with LogContext(project_id="proj-custom", request_id="req-custom-999"):
        try:
            numbers = [1, 2, 3]
            item = numbers[10]
        except IndexError as e:
            # Note: Using logger.error() with exception object triggers custom SecopsLogger.error()
            logger.error(e)
    print()
    
    # Minimal assertion: verify error was logged
    assert len(caplog.records) > 0, "No error logs were captured"
    assert any(record.levelname == "ERROR" for record in caplog.records)


def test_multi_line_messages(caplog):
    """Test logging with multi-line messages."""
    print("=" * 70)
    print("TEST 8: Multi-line Messages")
    print("=" * 70)
    
    with LogContext(project_id="proj-multiline"):
        long_message = """
        This is a multi-line log message.
        It spans multiple lines.
        Useful for detailed error descriptions.
        """
        logger.info(long_message)
        
        logger.warning("Processing items:\n  - Item 1\n  - Item 2\n  - Item 3")
    print()
    
    # Minimal assertion: verify multi-line logs were generated
    assert len(caplog.records) >= 2, "Expected at least 2 log records"
    assert any("multi-line" in record.message for record in caplog.records)


def test_complex_scenario(caplog):
    """Test a complex real-world scenario."""
    print("=" * 70)
    print("TEST 9: Complex Real-World Scenario")
    print("=" * 70)
    
    with LogContext(project_id="github-sync", user_id="system"):
        logger.info("Starting GitHub repository sync")
        
        repos = ["repo-1", "repo-2", "repo-3"]
        for repo in repos:
            with LogContext(request_id=f"sync-{repo}"):
                logger.info(f"Syncing repository: {repo}")
                logger.debug(f"Fetching commits for {repo}")
                
                if repo == "repo-2":
                    logger.warning(f"Repository {repo} has no recent commits")
                else:
                    logger.info(f"Successfully synced {repo}")
        
        logger.info("GitHub sync completed")
    print()
    
    # Minimal assertion: verify complex scenario generated multiple logs
    assert len(caplog.records) > 5, "Expected multiple log records from complex scenario"
    assert any("Starting GitHub repository sync" in record.message for record in caplog.records)
    assert any("GitHub sync completed" in record.message for record in caplog.records)


def test_no_context(caplog):
    """Test logging without any context."""
    print("=" * 70)
    print("TEST 10: Logs Without Context (Baseline)")
    print("=" * 70)
    
    logger.info("This log has no context variables")
    logger.debug("Debugging without context")
    logger.warning("Warning without context")
    print()
    
    # Minimal assertion: verify logs without context were generated
    assert len(caplog.records) >= 1, "Expected at least 1 log record"
