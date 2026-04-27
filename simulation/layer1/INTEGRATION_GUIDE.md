# Real-World Integration Guide

This guide shows how to use the refactored models for real-world data integration scenarios.

## Table of Contents
1. [REST API Integration](#rest-api-integration)
2. [Kafka Stream Processing](#kafka-stream-processing)
3. [Webhook Handler](#webhook-handler)
4. [CSV/Excel Import](#csvexcel-import)
5. [LDAP/Active Directory Sync](#ldapactive-directory-sync)

---

## REST API Integration

### Scenario: Sync employees from HR API

```python
import requests
from neo4j import GraphDatabase
from models import Person, Relationship, merge_person, merge_relationship, create_constraints

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
HR_API_BASE = "https://api.company.com/hr/v1"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def sync_employees():
    """Fetch employees from HR API and sync to Neo4j."""
    with driver.session() as session:
        # Ensure constraints exist
        create_constraints(session)
        
        # Fetch paginated employee data
        page = 1
        while True:
            response = requests.get(
                f"{HR_API_BASE}/employees",
                params={"page": page, "per_page": 100}
            )
            
            if response.status_code != 200:
                break
            
            data = response.json()
            if not data['employees']:
                break
            
            # Process each employee
            for emp in data['employees']:
                person = Person(
                    id=f"person_{emp['employee_id']}",
                    name=f"{emp['first_name']} {emp['last_name']}",
                    email=emp['email'],
                    title=emp['job_title'],
                    role=emp['role'],
                    seniority=emp['level'],
                    hire_date=emp['hire_date'],
                    is_manager=emp.get('is_manager', False)
                )
                
                # Create relationships if team is specified
                relationships = []
                if emp.get('team_id'):
                    relationships.append(Relationship(
                        type="MEMBER_OF",
                        from_id=person.id,
                        to_id=f"team_{emp['team_id']}",
                        from_type="Person",
                        to_type="Team"
                    ))
                
                if emp.get('manager_id'):
                    relationships.append(Relationship(
                        type="REPORTS_TO",
                        from_id=person.id,
                        to_id=f"person_{emp['manager_id']}",
                        from_type="Person",
                        to_type="Person"
                    ))
                
                # Merge person with relationships
                merge_person(session, person, relationships=relationships)
                print(f"✓ Synced {person.name}")
            
            page += 1

if __name__ == "__main__":
    sync_employees()
    driver.close()
```

---

## Kafka Stream Processing

### Scenario: Process employee events from Kafka

```python
from kafka import KafkaConsumer
import json
from neo4j import GraphDatabase
from models import Person, Relationship, merge_person, merge_relationship, create_constraints

# Configuration
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
KAFKA_BOOTSTRAP = "localhost:9092"
KAFKA_TOPIC = "employee-events"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def process_employee_event(event: dict, session):
    """Process a single employee event."""
    event_type = event['type']
    data = event['data']
    
    if event_type == "employee.created":
        person = Person(
            id=f"person_{data['employee_id']}",
            name=data['name'],
            email=data['email'],
            title=data['title'],
            role=data['role'],
            seniority=data['seniority'],
            hire_date=data['hire_date'],
            is_manager=data.get('is_manager', False)
        )
        merge_person(session, person)
        print(f"✓ Created person: {person.name}")
    
    elif event_type == "employee.team_assigned":
        rel = Relationship(
            type="MEMBER_OF",
            from_id=f"person_{data['employee_id']}",
            to_id=f"team_{data['team_id']}",
            from_type="Person",
            to_type="Team"
        )
        merge_relationship(session, rel)
        print(f"✓ Assigned employee {data['employee_id']} to team {data['team_id']}")
    
    elif event_type == "employee.manager_changed":
        rel = Relationship(
            type="REPORTS_TO",
            from_id=f"person_{data['employee_id']}",
            to_id=f"person_{data['manager_id']}",
            from_type="Person",
            to_type="Person"
        )
        merge_relationship(session, rel)
        print(f"✓ Updated manager for employee {data['employee_id']}")

def consume_events():
    """Consume events from Kafka and process them."""
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        group_id='neo4j-sync-group'
    )
    
    with driver.session() as session:
        create_constraints(session)
        
        print(f"Listening for events on {KAFKA_TOPIC}...")
        for message in consumer:
            try:
                event = message.value
                process_employee_event(event, session)
            except Exception as e:
                print(f"✗ Error processing event: {e}")

if __name__ == "__main__":
    try:
        consume_events()
    finally:
        driver.close()
```

---

## Webhook Handler

### Scenario: FastAPI webhook endpoint for org changes

```python
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from neo4j import GraphDatabase
from models import Person, Team, Relationship, merge_person, merge_team, merge_relationship, create_constraints

app = FastAPI()

# Neo4j connection
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

class EmployeeWebhook(BaseModel):
    event: str
    employee_id: str
    name: str
    email: str
    title: str
    role: str
    seniority: str
    hire_date: str
    is_manager: bool = False
    team_id: str | None = None
    manager_id: str | None = None

@app.on_event("startup")
async def startup():
    """Initialize Neo4j constraints."""
    with driver.session() as session:
        create_constraints(session)

@app.post("/webhooks/employee")
async def handle_employee_webhook(webhook: EmployeeWebhook, background_tasks: BackgroundTasks):
    """Handle employee webhook events."""
    background_tasks.add_task(process_employee_webhook, webhook)
    return {"status": "accepted"}

def process_employee_webhook(webhook: EmployeeWebhook):
    """Process employee webhook in background."""
    with driver.session() as session:
        person = Person(
            id=f"person_{webhook.employee_id}",
            name=webhook.name,
            email=webhook.email,
            title=webhook.title,
            role=webhook.role,
            seniority=webhook.seniority,
            hire_date=webhook.hire_date,
            is_manager=webhook.is_manager
        )
        
        relationships = []
        
        if webhook.team_id:
            relationships.append(Relationship(
                type="MEMBER_OF",
                from_id=person.id,
                to_id=f"team_{webhook.team_id}",
                from_type="Person",
                to_type="Team"
            ))
        
        if webhook.manager_id:
            relationships.append(Relationship(
                type="REPORTS_TO",
                from_id=person.id,
                to_id=f"person_{webhook.manager_id}",
                from_type="Person",
                to_type="Person"
            ))
        
        merge_person(session, person, relationships=relationships)
        print(f"✓ Processed webhook for {person.name}")

@app.on_event("shutdown")
async def shutdown():
    """Close Neo4j driver."""
    driver.close()
```

---

## CSV/Excel Import

### Scenario: Import employees from CSV file

```python
import csv
from neo4j import GraphDatabase
from models import Person, merge_person, create_constraints

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

def import_csv(csv_path: str):
    """Import employees from CSV file."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            create_constraints(session)
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    person = Person(
                        id=f"person_{row['employee_id']}",
                        name=f"{row['first_name']} {row['last_name']}",
                        email=row['email'],
                        title=row['title'],
                        role=row['role'],
                        seniority=row['seniority'],
                        hire_date=row['hire_date'],
                        is_manager=row['is_manager'].lower() == 'true'
                    )
                    
                    merge_person(session, person)
                    print(f"✓ Imported {person.name}")
    
    finally:
        driver.close()

if __name__ == "__main__":
    import_csv("employees.csv")
```

**Sample CSV format:**
```csv
employee_id,first_name,last_name,email,title,role,seniority,hire_date,is_manager
1001,John,Doe,john.doe@company.com,Software Engineer,Engineer,Mid,2024-01-15,false
1002,Jane,Smith,jane.smith@company.com,Senior Engineer,Engineer,Senior,2023-05-10,false
```

---

## LDAP/Active Directory Sync

### Scenario: Sync organization structure from LDAP

```python
from ldap3 import Server, Connection, ALL
from neo4j import GraphDatabase
from models import Person, Team, Relationship, merge_person, merge_team, merge_relationship, create_constraints

# Configuration
LDAP_SERVER = "ldap://ldap.company.com"
LDAP_USER = "cn=admin,dc=company,dc=com"
LDAP_PASSWORD = "password"
LDAP_BASE_DN = "ou=people,dc=company,dc=com"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

def sync_from_ldap():
    """Sync organization from LDAP/AD."""
    # Connect to LDAP
    server = Server(LDAP_SERVER, get_info=ALL)
    ldap_conn = Connection(server, LDAP_USER, LDAP_PASSWORD, auto_bind=True)
    
    # Connect to Neo4j
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        with driver.session() as session:
            create_constraints(session)
            
            # Search for all users
            ldap_conn.search(
                search_base=LDAP_BASE_DN,
                search_filter='(objectClass=person)',
                attributes=['cn', 'mail', 'title', 'department', 'manager']
            )
            
            for entry in ldap_conn.entries:
                # Extract person data
                person = Person(
                    id=f"person_{entry.cn.value.lower().replace(' ', '_')}",
                    name=entry.cn.value,
                    email=entry.mail.value if entry.mail else "",
                    title=entry.title.value if entry.title else "Employee",
                    role="Employee",
                    seniority="Mid",  # Default, could parse from title
                    hire_date="2024-01-01",  # Would need to get from HR system
                    is_manager=False
                )
                
                relationships = []
                
                # Add department relationship
                if entry.department:
                    relationships.append(Relationship(
                        type="MEMBER_OF",
                        from_id=person.id,
                        to_id=f"team_{entry.department.value.lower().replace(' ', '_')}",
                        from_type="Person",
                        to_type="Team"
                    ))
                
                # Add manager relationship
                if entry.manager:
                    manager_cn = entry.manager.value.split(',')[0].split('=')[1]
                    relationships.append(Relationship(
                        type="REPORTS_TO",
                        from_id=person.id,
                        to_id=f"person_{manager_cn.lower().replace(' ', '_')}",
                        from_type="Person",
                        to_type="Person"
                    ))
                
                merge_person(session, person, relationships=relationships)
                print(f"✓ Synced {person.name}")
    
    finally:
        ldap_conn.unbind()
        driver.close()

if __name__ == "__main__":
    sync_from_ldap()
```

---

## Best Practices

### 1. Error Handling
```python
def safe_merge_person(session, person_data):
    """Merge person with error handling."""
    try:
        person = Person(**person_data)
        merge_person(session, person)
        return True
    except KeyError as e:
        print(f"Missing required field: {e}")
        return False
    except Exception as e:
        print(f"Error merging person: {e}")
        return False
```

### 2. Batch Processing with Sessions
```python
# Reuse session for better performance
with driver.session() as session:
    create_constraints(session)
    
    for person_data in large_dataset:
        person = Person(**person_data)
        merge_person(session, person)
        
        # Commit every 100 records
        if len(large_dataset) % 100 == 0:
            print(f"Processed {len(large_dataset)} records")
```

### 3. Incremental Sync
```python
def incremental_sync(last_sync_time):
    """Sync only changed records since last sync."""
    response = requests.get(
        f"{API_BASE}/employees",
        params={"updated_since": last_sync_time}
    )
    
    with driver.session() as session:
        for emp in response.json()['employees']:
            # Process only changed records
            ...
```

### 4. Validation
```python
from typing import Optional

def validate_person_data(data: dict) -> Optional[Person]:
    """Validate person data before creating dataclass."""
    required_fields = ['id', 'name', 'email', 'title', 'role', 'seniority', 'hire_date']
    
    for field in required_fields:
        if field not in data:
            print(f"Missing required field: {field}")
            return None
    
    try:
        return Person(**data)
    except TypeError as e:
        print(f"Invalid data type: {e}")
        return None
```

---

## Performance Tips

1. **Use transactions for bulk operations**: Keep session open for related operations
2. **Create constraints early**: Before bulk loading
3. **Use MERGE wisely**: MERGE is idempotent but slower than CREATE
4. **Batch similar operations**: Process all people, then all teams, then relationships
5. **Monitor Neo4j performance**: Use `PROFILE` queries to optimize

---

## Monitoring and Logging

```python
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def merge_person_with_logging(session, person):
    """Merge person with logging."""
    start_time = datetime.now()
    
    try:
        merge_person(session, person)
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Merged person {person.id} in {duration:.2f}s")
        return True
    except Exception as e:
        logger.error(f"Failed to merge person {person.id}: {e}")
        return False
```
