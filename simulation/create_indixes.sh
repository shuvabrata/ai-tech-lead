#!/bin/bash

# Create all recommended indexes for the project graph database
# This script wraps the Python implementation

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=================================================="
echo "Creating Indexes for Project Graph Database"
echo "=================================================="
echo ""

# Check if Python script exists
if [ ! -f "$SCRIPT_DIR/create_indexes.py" ]; then
    echo "❌ Error: create_indexes.py not found in $SCRIPT_DIR"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed or not in PATH"
    exit 1
fi

# Run the Python script
python3 "$SCRIPT_DIR/create_indexes.py"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ All indexes created successfully!"
else
    echo ""
    echo "❌ Index creation failed with exit code $exit_code"
    exit $exit_code
fi
