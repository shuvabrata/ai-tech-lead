import pytest
from unittest.mock import patch, Mock
import os
import requests

# It's good practice to set the path for module imports
import sys
from pathlib import Path

# Add the 'app' directory to the Python path to import modules
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root / 'app'))

from connectors.modules.github.main import load_config_from_server, main as github_main

# --- Tests for load_config_from_server (converted to pytest style) ---

@patch('connectors.modules.github.main.requests.get')
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

@patch('connectors.modules.github.main.requests.get')
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

# --- New tests for main() config logic ---

@patch('connectors.modules.github.main.GraphDatabase.driver')
@patch('connectors.modules.github.main.load_config_from_file')
@patch('connectors.modules.github.main.load_config_from_server')
def test_main_config_source_server(mock_load_server, mock_load_file, mock_driver, monkeypatch):
    """
    Test main() when CONFIGURATION_SOURCE is 'SERVER'.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "SERVER")
    mock_load_server.return_value = {"repos": []}  # A valid config to proceed
    
    github_main()

    mock_load_server.assert_called_once()
    mock_load_file.assert_not_called()
    mock_driver.assert_called_once()  # Ensure main proceeds to driver init

@patch('connectors.modules.github.main.GraphDatabase.driver')
@patch('connectors.modules.github.main.validate_config', return_value=True)
@patch('connectors.modules.github.main.Path.is_file', return_value=True)
@patch('connectors.modules.github.main.load_config_from_file')
@patch('connectors.modules.github.main.load_config_from_server')
def test_main_config_source_file_success(mock_load_server, mock_load_file, mock_is_file, mock_validate, mock_driver, monkeypatch):
    """
    Test main() when CONFIGURATION_SOURCE is 'FILE' and the file is valid.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "FILE")
    mock_load_file.return_value = {"repos": []}

    github_main()

    mock_load_server.assert_not_called()
    mock_is_file.assert_called_once()
    mock_validate.assert_called_once()
    mock_load_file.assert_called_once()
    mock_driver.assert_called_once()

@patch('connectors.modules.github.main.GraphDatabase.driver')
@patch('connectors.modules.github.main.validate_config')
@patch('connectors.modules.github.main.Path.is_file', return_value=False)
@patch('connectors.modules.github.main.load_config_from_file')
@patch('connectors.modules.github.main.load_config_from_server')
def test_main_config_source_file_not_found(mock_load_server, mock_load_file, mock_is_file, mock_validate, mock_driver, monkeypatch, caplog):
    """
    Test main() when CONFIGURATION_SOURCE is 'FILE' and the file is missing.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "FILE")
    
    github_main()

    mock_load_server.assert_not_called()
    mock_is_file.assert_called_once()
    mock_validate.assert_not_called()
    mock_load_file.assert_not_called()
    mock_driver.assert_not_called()  # Should exit before driver is called
    assert "Configuration file not found" in caplog.text

@patch('connectors.modules.github.main.GraphDatabase.driver')
@patch('connectors.modules.github.main.validate_config', return_value=False)
@patch('connectors.modules.github.main.Path.is_file', return_value=True)
@patch('connectors.modules.github.main.load_config_from_file')
@patch('connectors.modules.github.main.load_config_from_server')
def test_main_config_source_file_invalid(mock_load_server, mock_load_file, mock_is_file, mock_validate, mock_driver, monkeypatch, caplog):
    """
    Test main() when CONFIGURATION_SOURCE is 'FILE' and the file is invalid.
    """
    monkeypatch.setenv("CONFIGURATION_SOURCE", "FILE")

    github_main()

    mock_load_server.assert_not_called()
    mock_is_file.assert_called_once()
    mock_validate.assert_called_once()
    mock_load_file.assert_not_called()
    mock_driver.assert_not_called()  # Should exit before driver is called
    assert "Configuration validation failed" in caplog.text