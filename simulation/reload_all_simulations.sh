#!/bin/bash

# Script to reload all simulation data from scratch
# Layer 1 clears the entire database, then subsequent layers are loaded

set -e  # Exit on error

echo "Starting complete data reload..."
echo "================================"

cd "$(dirname "$0")"

run_layer() {
	local step="$1"
	local total="$2"
	local dir="$3"
	local label="$4"

	echo -e "\n[${step}/${total}] Loading ${label}..."
	(
		cd "$dir"
		python generate_data.py
		python load_to_neo4j.py
	)
}

run_layer 1 8 layer1 "Layer 1: People & Teams (clears entire database)"
run_layer 2 8 layer2 "Layer 2: Jira Initiatives"
run_layer 3 8 layer3 "Layer 3: Jira Epics"
run_layer 4 8 layer4 "Layer 4: Jira Stories & Bugs"
run_layer 5 8 layer5 "Layer 5: Git Repositories"
run_layer 6 8 layer6 "Layer 6: Git Branches"
run_layer 7 8 layer7 "Layer 7: Git Commits & Files"
run_layer 8 8 layer8 "Layer 8: Pull Requests"

echo -e "\n================================"
echo "✓ All layers loaded successfully!"
echo "Open http://localhost:7474 to explore the data"
