import pytest
from unittest.mock import patch, Mock
import os
import requests

# Add the 'app' directory to the Python path to import modules
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root / 'app'))

from connectors.producers.jira_producer import load_config_from_server

# --- Tests for load_config_from_server ---

@patch('connectors.producers.jira.jira_config.requests.get')
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

@patch('connectors.producers.jira.jira_config.requests.get')
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


