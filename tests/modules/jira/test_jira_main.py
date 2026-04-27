import pytest
from unittest.mock import patch, Mock
import os
import requests

# Add the 'app' directory to the Python path to import modules
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root / 'app'))

from modules.jira.main import load_config_from_server, main as jira_main

# --- Tests for load_config_from_server ---

@patch('modules.jira.main.requests.get')
def test_load_config_from_server_success(mock_get, monkeypatch):
    """
    Test successful configuration loading from the server for Jira.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock the API response
    mock_api_response = [
        {
            "id": 1,
            "url": "https://test.atlassian.net",
            "email": "test@example.com",
            "api_token": "token123"
        }
    ]
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_api_response
    mock_get.return_value = mock_response

    # Call the function
    config = load_config_from_server()

    # Assertions
    expected_config = {
        "account": [
            {
                "id": 1,
                "url": "https://test.atlassian.net",
                "email": "test@example.com",
                "api_token": "token123"
            }
        ]
    }
    assert config == expected_config
    
    # Verify requests.get was called correctly
    mock_get.assert_called_once_with(
        "http://mock-server:8000/api/v1/connectors/jira/configs",
        params={'include_secrets': 'true'},
        timeout=10
    )

@patch('modules.jira.main.requests.get')
def test_load_config_from_server_http_error(mock_get, monkeypatch):
    """
    Test handling of an HTTP error from the server for Jira.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock a failed API response
    mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

    # Assert that the correct exception is raised
    with pytest.raises(requests.exceptions.HTTPError):
        load_config_from_server()

# --- New tests for main() config logic ---

def setup_downstream_mocks(mock_jira_conn, mock_driver):
    """Helper to set up mocks for calls made after config loading."""
    mock_jira_conn.return_value.myself.return_value = {"displayName": "test"}
    # Mock fetch functions to return empty lists to prevent further processing
    mock_jira_conn.return_value.get.return_value = {'values': [], 'total': 0}
    mock_jira_conn.return_value.enhanced_jql.return_value = {'issues': []}

    mock_driver_instance = mock_driver.return_value
    mock_driver_instance.verify_connectivity.return_value = None
    mock_session = mock_driver_instance.session.return_value
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = None


@patch('modules.jira.main.GraphDatabase.driver')
@patch('modules.jira.main.create_jira_connection')
@patch('modules.jira.main.load_config_from_file')
@patch('modules.jira.main.load_config_from_server')
def test_main_config_source_server(mock_load_server, mock_load_file, mock_jira_conn, mock_driver, monkeypatch):
    """
    Test jira_main() when CONFIGURATION_SOURCE is 'SERVER'.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "SERVER")
    # A valid config to proceed
    mock_load_server.return_value = {"account": [{"url": "u", "email": "e", "api_token": "t"}]}
    setup_downstream_mocks(mock_jira_conn, mock_driver)
    
    return_code = jira_main()

    mock_load_server.assert_called_once()
    mock_load_file.assert_not_called()
    mock_jira_conn.assert_called_once()
    mock_driver.assert_called_once()
    assert return_code == 0, "main() should return 0 on success"

@patch('modules.jira.main.GraphDatabase.driver')
@patch('modules.jira.main.create_jira_connection')
@patch('modules.jira.main.load_config_from_file')
@patch('modules.jira.main.load_config_from_server')
def test_main_config_source_file_success(mock_load_server, mock_load_file, mock_jira_conn, mock_driver, monkeypatch):
    """
    Test jira_main() when CONFIGURATION_SOURCE is 'FILE' and the file is valid.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "FILE")
    mock_load_file.return_value = {"account": [{"url": "u", "email": "e", "api_token": "t"}]}
    setup_downstream_mocks(mock_jira_conn, mock_driver)

    return_code = jira_main()

    mock_load_server.assert_not_called()
    mock_load_file.assert_called_once()
    mock_jira_conn.assert_called_once()
    mock_driver.assert_called_once()
    assert return_code == 0, "main() should return 0 on success"

@patch('modules.jira.main.GraphDatabase.driver')
@patch('modules.jira.main.create_jira_connection')
@patch('modules.jira.main.load_config_from_file', side_effect=FileNotFoundError("File not found"))
@patch('modules.jira.main.load_config_from_server')
def test_main_config_source_file_not_found(mock_load_server, mock_load_file, mock_jira_conn, mock_driver, monkeypatch, caplog):
    """
    Test jira_main() when CONFIGURATION_SOURCE is 'FILE' and the file is missing.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "FILE")
    
    return_code = jira_main()

    mock_load_server.assert_not_called()
    mock_load_file.assert_called_once()
    mock_jira_conn.assert_not_called()
    mock_driver.assert_not_called()
    assert "Configuration file not found" in caplog.text
    assert return_code == 1, "main() should return 1 on config error"

@patch('modules.jira.main.GraphDatabase.driver')
@patch('modules.jira.main.create_jira_connection')
@patch('modules.jira.main.load_config_from_server', side_effect=Exception("Generic load error"))
def test_main_config_source_server_load_error(mock_load_server, mock_jira_conn, mock_driver, monkeypatch, caplog):
    """
    Test jira_main() when CONFIGURATION_SOURCE is 'SERVER' and loading fails.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "SERVER")
    
    return_code = jira_main()

    mock_load_server.assert_called_once()
    mock_jira_conn.assert_not_called()
    mock_driver.assert_not_called()
    assert "A critical error occurred during configuration loading" in caplog.text
    assert return_code == 1, "main() should return 1 on config error"