# Neo4j Desktop Installation Guide
**Purpose**: Use Neo4j Desktop for Bloom visualization alongside Docker Neo4j  
**Date**: January 11, 2026  
**Setup**: Single instance at a time - either Docker OR Desktop (keeps it simple)

---

## Overview

This setup allows you to:
- Run **either** Docker Neo4j **or** Neo4j Desktop at any given time (not both)
- Both use **default ports** (`localhost:7687` for Bolt, `localhost:7474` for Browser)
- Switch between them as needed:
  - **Docker**: For development and testing
  - **Desktop**: For Bloom visualization and exploration
- Keep scripts simple - always connect to `bolt://localhost:7687`
- Load data to whichever instance is currently running

---

## Installation Steps

### 1. Download Neo4j Desktop
1. Go to: https://neo4j.com/download/
2. Click **"Download Neo4j Desktop"**
3. Fill in the form (free, no credit card needed)
4. Download the Windows installer
5. Save the **activation key** they email you

### 2. Install on Windows
1. Run the downloaded installer (`Neo4j Desktop Setup.exe`)
2. Follow installation wizard
3. Accept license agreement
4. Choose installation location (default is fine)
5. Complete installation

### 3. First Launch Setup
1. Launch Neo4j Desktop
2. **Note**: Activation key may or may not be required (depends on version)
   - If prompted for activation key, enter it from your email
   - If no prompt appears, proceed directly to creating databases
3. You're now ready to create databases

---

## Database Setup

### 1. Create Project and Database
Use Neo4j Desktop's UI to create a new project and add a local database. Set a password you'll remember - you'll need it for the Python scripts.

**Note**: Keep the **default ports** (7687, 7474) - no port configuration needed!

### 2. Start the Database
1. **Important**: Make sure Docker Neo4j is **stopped** first
   ```bash
   # From WSL, stop Docker Neo4j:
   docker compose down
   ```
2. Start the Desktop database using the **Start** button
3. Wait for status to show **Running**
4. You should now see buttons to open with Browser or Bloom

---

## Accessing Bloom

### 1. Open Bloom
1. Ensure database is **Running**
2. Click **"Open with Neo4j Bloom"**
3. Bloom opens in a new window

### 2. First-Time Bloom Setup
1. **Perspective**: Bloom will prompt you to create a perspective
2. Click **"Generate Perspective"** (after data is loaded)
3. Bloom auto-discovers your node types and relationships
4. Save the perspective

### 3. Basic Bloom Usage
- **Search**: Type queries like "Person" or "Team" in the search bar
- **Explore**: Click nodes to expand relationships
- **Visualize**: Drag nodes to organize the graph layout
- **Filter**: Use the filter panel on the left
- **Style**: Right-click nodes to change colors/sizes

---

## Connection Details

**Both Docker and Desktop use the same ports** (only one runs at a time):

```
URI:      bolt://localhost:7687
Browser:  http://localhost:7474/browser/
User:     neo4j
Password: <your-password>
```

**Note**: Passwords can be different between Docker and Desktop instances - just remember which one you're using!

---

## Loading Data

### Whichever instance is running gets the data

Since both use the same ports, your scripts always connect to `bolt://localhost:7687`:

```bash
cd /home/shuva/github/shuvabrata/enterprise-graph/simulation

# Load all layers (works for whichever instance is running)
./reload_all.sh

# Or load individual layers
python layer1/load_to_neo4j.py
python layer2/load_to_neo4j.py
# etc.
```
