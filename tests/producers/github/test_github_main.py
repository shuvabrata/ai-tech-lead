import pytest
from unittest.mock import patch, Mock
import os
import requests

from connectors.producers.github.github_config import load_config_from_server

# --- Tests for load_config_from_server (converted to pytest style) ---

@patch('connectors.producers.github.github_config.requests.get')
def test_load_config_from_server_success(mock_get, monkeypatch):
    """
    Test successful configuration loading from the server.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock the API response
    mock_api_response = [
        {
            "id": 1,
            "url": "https://github.com/test/repo1",
            "access_token": "token123",
            "branch_name_patterns": ["main"],
            "extraction_sources": ["branch"]
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
        "repos": [
            {
                "url": "https://github.com/test/repo1",
                "access_token": "token123",
                "branch_name_patterns": ["main"],
                "extraction_sources": ["branch"],
                "search_filters": {}
            }
        ]
    }
    assert config == expected_config
    
    # Verify requests.get was called correctly
    mock_get.assert_called_once_with(
        "http://mock-server:8000/api/v1/connectors/github/configs",
        params={'include_secrets': 'true'},
        timeout=10
    )

@patch('connectors.producers.github.github_config.requests.get')
def test_load_config_from_server_http_error(mock_get, monkeypatch):
    """
    Test handling of an HTTP error from the server.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock a failed API response
    mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

    # Assert that the correct exception is raised
    with pytest.raises(requests.exceptions.HTTPError):
        load_config_from_server()

