#!/bin/bash
# Quick start script to run property validation tests

set -e  # Exit on error

# Ensure we're in the project root
cd "$(dirname "$0")/.."


# Check if Neo4j credentials are set
if [ -z "$NEO4J_PASSWORD" ]; then
    echo "⚠️  Warning: NEO4J_PASSWORD environment variable not set"
    echo "   Set it by running: export NEO4j_PASSWORD='your_password'"
    echo "   Or add it to .env file"
    exit 1
fi

echo "🚀 Running Property Validation Tests..."
echo ""

# Run the tests with verbose output
pytest tests/property_validation/test_property_validation.py -v -s

echo ""
echo "✅ Tests complete!"
echo ""
echo "📊 Reports generated:"
echo "   - JSON: tests/property_validation/results/report.json"
echo "   - HTML: tests/property_validation/results/report.html"
echo ""
echo "To view HTML report, open: tests/property_validation/results/report.html"
