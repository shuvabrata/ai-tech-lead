#!/bin/bash
# Reset Neo4j Database
# Clears all nodes and relationships from the database

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to project root (parent of scripts/)
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Navigate to simulation/layer1 and run reset
cd "$PROJECT_ROOT/simulation/layer1"
python3 reset_db.py
