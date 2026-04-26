#!/bin/bash
# Initialize configuration files from examples
# This script helps set up .config.json files for GitHub and Jira syncing

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GITHUB_CONFIG="$PROJECT_ROOT/app/modules/github/.config.json"
GITHUB_EXAMPLE="$PROJECT_ROOT/app/modules/github/.config.json.example"
JIRA_CONFIG="$PROJECT_ROOT/app/modules/jira/.config.json"
JIRA_EXAMPLE="$PROJECT_ROOT/app/modules/jira/.config.json.example"

echo "========================================"
echo "Enterprise Graph - Config Initialization"
echo "========================================"
echo ""

# Function to copy config if it doesn't exist
init_config() {
    local config_file=$1
    local example_file=$2
    local name=$3
    
    if [ -f "$config_file" ]; then
        echo "✓ $name config already exists: $config_file"
    elif [ -d "$config_file" ]; then
        echo "✗ ERROR: $config_file exists as a directory (likely created by Docker)"
        echo "  Please remove it first: sudo rm -rf $config_file"
        return 1
    else
        if [ -f "$example_file" ]; then
            cp "$example_file" "$config_file"
            echo "✓ Created $name config from example: $config_file"
            echo "  ⚠️  IMPORTANT: Edit this file and add your credentials!"
        else
            echo "✗ ERROR: Example file not found: $example_file"
            return 1
        fi
    fi
}

# Initialize GitHub config
echo "GitHub Configuration:"
if init_config "$GITHUB_CONFIG" "$GITHUB_EXAMPLE" "GitHub"; then
    echo ""
else
    exit 1
fi

# Initialize Jira config
echo "Jira Configuration:"
if init_config "$JIRA_CONFIG" "$JIRA_EXAMPLE" "Jira"; then
    echo ""
else
    exit 1
fi

echo "========================================"
echo "✓ Configuration initialization complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Edit app/modules/github/.config.json with your GitHub credentials"
echo "2. Edit app/modules/jira/.config.json with your Jira credentials"
echo "3. See USER_GUIDE.md for detailed instructions on obtaining API tokens"
echo ""
