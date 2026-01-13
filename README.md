# Neo4j Tax/AML Knowledge Graph

Production-grade knowledge graph system for tax compliance, AML (Anti-Money Laundering), and KYC (Know Your Customer) investigations.

## Architecture Overview

This system implements a **clean, layered architecture** designed for large-scale graph databases:

```
┌─────────────────────────────────────────┐
│           Services Layer                │
│  (Business Logic & Orchestration)       │
│  - IngestionService                     │
│  - ProfileService                       │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│       Repositories Layer                │
│  (Graph Operations by Type)             │
│  - RegistryRepository (Identity/MERGE)  │
│  - GraphMutationRepository (Facts)      │
│  - ReadRepository (Simple Queries)      │
│  - TraversalRepository (Multi-hop)      │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│          Domain Layer                   │
│  (Pure Domain Models & Enums)           │
│  - models.py (Entities & Views)         │
│  - enums.py (Controlled Vocabularies)   │
└─────────────────────────────────────────┘
```

### Why This Architecture?

**Repository Pattern by Operation Type** (not by entity):
- ✅ **RegistryRepository**: Identity management (MERGE operations)
- ✅ **GraphMutationRepository**: Relationship creation (facts)
- ✅ **ReadRepository**: Simple entity queries
- ✅ **TraversalRepository**: Complex multi-hop graph traversals

**Benefits**:
1. **Clear separation of concerns**: Each repository has one responsibility
2. **Optimized for Neo4j**: Uses execute_read/execute_write correctly
3. **Prevents Cypher sprawl**: All queries in one place per operation type
4. **Easy to test**: Mock one repository to test services
5. **LLM-safe**: No direct LLM-to-database access possible

---

## Graph Schema

### Node Types

| Node Label | Identity Key | Purpose |
|------------|--------------|---------|
| **Person** | `rnokpp` (tax ID) | Natural persons (taxpayers, directors, family) |
| **Organization** | `edrpou` (company code) | Legal entities (companies, government agencies) |
| **IncomeRecord** | `income_id` (synthetic) | Individual income payment events |
| **Property** | `property_id` (synthetic) | Real estate or vehicles |
| **Request** | `request_id` | Investigation requests |
| **Executor** | `executor_rnokpp` | Investigators conducting inquiries |
| **PowerOfAttorney** | `poa_id` (synthetic) | Legal power of attorney documents |

### Relationship Types

| Relationship | Direction | Meaning |
|--------------|-----------|---------|
| **DIRECTOR_OF** | Person → Organization | Person is director/head of company |
| **FOUNDER_OF** | Person → Organization | Person is founder/shareholder |
| **CHILD_OF** | Person → Person | Family relationship (child → parent) |
| **SPOUSE_OF** | Person ↔ Person | Marriage (bidirectional) |
| **EARNED_INCOME** | Person → IncomeRecord | Person earned this income |
| **PAID_BY** | IncomeRecord → Organization | Income paid by this tax agent |
| **OWNS** | Person → Property | Direct property ownership |
| **GRANTOR_OF** | Person → PowerOfAttorney | Person granted PoA |
| **REPRESENTATIVE_OF** | Person → PowerOfAttorney | Person received PoA (can act on behalf) |
| **AUTHORIZES_PROPERTY** | PowerOfAttorney → Property | PoA covers this property |
| **CREATED_REQUEST** | Executor → Request | Investigator created this request |
| **SUBJECT_OF** | Request → Person | Request investigates this person |

### Design Decisions

**Why IncomeRecord as Node (not relationship)?**
- ✅ Each payment is a queryable fact with many attributes
- ✅ Enables temporal queries: "show income trend over time"
- ✅ Prevents relationship property explosion
- ❌ **Alternative rejected**: Person-[:RECEIVED_INCOME {amount, tax, ...}]->Organization would create hundreds of relationships between same nodes

**Why separate Executor from Person?**
- ✅ Executors are investigators, not subjects - different domain role
- ✅ Prevents query confusion - clear separation of concerns
- ✅ Different access control requirements in production

**Income Relationship Pattern**:
```
Person -[:EARNED_INCOME]-> IncomeRecord -[:PAID_BY]-> Organization
```
WHY: Allows efficient queries in both directions with clear money flow semantics.

---

## Installation & Setup

### Prerequisites
```bash
# Neo4j 5+ required
docker run -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.15
```

### Environment Configuration
```bash
cp .env.example .env
# Edit .env with your Neo4j credentials
```

**.env:**
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
NEO4J_MAX_POOL_SIZE=50
NEO4J_CONNECTION_TIMEOUT_SEC=30
```

### Install Dependencies
```bash
pip install neo4j pydantic-settings
```

---

## Usage

### 1. Initialize Database Schema

```python
from core.neo4j_driver import init_driver, close_driver
from repositories.registry_repo import RegistryRepository

# Initialize driver (once per application)
init_driver()

# Create constraints and indexes
registry = RegistryRepository()
registry.ensure_constraints()

# Cleanup
close_driver()
```

### 2. Ingest Data

```python
from services.ingestion_service import IngestionService
from repositories.registry_repo import RegistryRepository
from repositories.mutation_repo import GraphMutationRepository

registry = RegistryRepository()
mutation = GraphMutationRepository()
ingestion = IngestionService(registry, mutation)

# Ingest from all_data.txt
with open("all_data.txt", "r", encoding="utf-8") as f:
    for line in f:
        ingestion.ingest_json_record(line)
```

### 3. Query Person Profile

```python
from services.profile_service import ProfileService
from repositories.read_repo import ReadRepository
from repositories.traversal_repo import TraversalRepository

read_repo = ReadRepository()
traversal_repo = TraversalRepository()
profile_service = ProfileService(read_repo, traversal_repo)

# Get comprehensive person profile
profile = profile_service.get_person_profile("1111111111")

if profile:
    print(f"Name: {profile.person.last_name} {profile.person.first_name}")
    print(f"Total Income: {profile.total_income_paid} UAH")
    print(f"Total Tax Paid: {profile.total_tax_paid} UAH")
    print(f"Controlled Organizations: {len(profile.organizations_director)}")
    print(f"Direct Properties: {len(profile.properties_direct)}")
    print(f"Family Members: {len(profile.children) + len(profile.parents)}")
```

### 4. Analyze Family Wealth

```python
# Aggregate wealth across family network
family_aggregate = profile_service.get_family_wealth_aggregate("1111111111", family_depth=2)

if family_aggregate:
    print(f"Family Members: {len(family_aggregate.family_members)}")
    print(f"Total Properties: {family_aggregate.total_properties}")
    print(f"Family Income: {family_aggregate.total_family_income} UAH")
    print(f"Controlled Companies: {len(family_aggregate.controlled_organizations)}")
```

### 5. Search and Investigate

```python
# Search persons by name
persons = read_repo.search_persons_by_name(last_name="АДЕЛЬРЕЇВ")

# Find co-directors (network analysis)
co_directors = traversal_repo.get_co_directors("2935512345")
for cd in co_directors:
    print(f"{cd['person'].last_name}: {cd['shared_count']} shared companies")

# Detect circular ownership
cycles = traversal_repo.find_circular_ownership(max_depth=5)
for cycle in cycles:
    print(f"Circular ownership detected: {' → '.join(cycle)}")
```

---

## Key Features

### 1. Schema Governance
- **Explicit, finite set** of node labels and relationship types (enums)
- **No dynamic schema creation** - all types defined upfront
- **Uniqueness constraints** enforce data integrity at database level

### 2. Identity Management
- **Stable unique identifiers** for all entities (RNOKPP, EDRPOU)
- **MERGE operations** prevent duplicates
- **Synthetic IDs** for entities without natural keys (income records, properties)

### 3. Graph-First Thinking
- **Nodes = real-world entities** (nouns): Person, Organization, Property
- **Relationships = facts/actions** (verbs): DIRECTOR_OF, EARNED_INCOME
- **Each relationship represents exactly one fact**

### 4. LLM Safety
- **NO direct LLM-to-database access**
- **Structured commands only** via services
- **Cypher generation by LLMs forbidden** - all queries pre-defined in repositories

### 5. Performance Optimization
- **Indexes on frequently queried fields** (names, dates)
- **Read-only transactions** for all queries (execute_read)
- **Write transactions** for mutations (execute_write)
- **Connection pooling** configured via environment

---

## Query Examples

### Find all income sources for a person
```cypher
MATCH (p:Person {rnokpp: "1111111111"})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
RETURN o.name, sum(i.income_paid) as total_paid, collect(i.period_year) as years
ORDER BY total_paid DESC
```

### Find undeclared beneficial owners
```cypher
MATCH (p:Person)-[:FOUNDER_OF]->(o:Organization)-[:FOUNDER_OF]-(other:Person)
WHERE NOT (p)-[:DIRECTOR_OF]->(o)
RETURN p, o, other
```

### Detect income/tax mismatches
```cypher
MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)
WHERE i.income_accrued <> i.income_paid
RETURN p.rnokpp, p.last_name, sum(i.income_accrued - i.income_paid) as unpaid
```

### Family wealth consolidation
```cypher
MATCH (p:Person {rnokpp: "1111111111"})-[:CHILD_OF|SPOUSE_OF*1..2]-(relative:Person)
MATCH (relative)-[:OWNS]->(prop:Property)
RETURN p.last_name as family, count(prop) as properties, collect(prop.description) as assets
```

---

## Design Principles (Mandatory)

### 1. Graph-First Thinking
- Nodes represent real-world entities (nouns)
- Relationships represent facts or actions (verbs)
- Each relationship represents exactly one fact

### 2. Schema Governance
- All node labels and relationship types explicitly defined
- No dynamic labels or relationships
- Use enums for relationship types and controlled vocabularies

### 3. Identity & Registry
- Each entity type has a stable unique identifier
- Use MERGE with constraints to prevent duplicates
- Names or textual fields must NEVER be used as identifiers

### 4. Repository Pattern (Neo4j Best Practices)
- Repositories organized by TYPE OF OPERATION, not by entity
- Minimum: RegistryRepository, GraphMutationRepository, ReadRepository, TraversalRepository
- Cypher and DB access ONLY in repositories
- Business logic strictly in services

### 5. Separation of Concerns
- Repositories: Cypher queries and database access
- Services: Business logic and orchestration
- Domain models: Pure data structures (no database logic)

### 6. LLM Safety
- No direct LLM-to-database access
- Structured commands handled by services only
- Cypher generation by LLMs strictly forbidden

---

## File Structure

```
neo4j/
├── domain/
│   ├── models.py          # Domain entities & computed views
│   └── enums.py           # Node labels, relationship types, vocabularies
├── repositories/
│   ├── registry_repo.py   # Identity/MERGE operations
│   ├── mutation_repo.py   # Relationship creation
│   ├── read_repo.py       # Simple entity queries
│   └── traversal_repo.py  # Multi-hop graph traversals
├── services/
│   ├── ingestion_service.py  # Data import & transformation
│   └── profile_service.py    # Profile aggregation
├── core/
│   ├── neo4j_driver.py    # Driver management
│   └── config.py          # Environment configuration
├── main.py                # Example usage
├── all_data.txt           # Source data (JSON lines)
├── SCHEMA_DESIGN.md       # Detailed schema documentation
└── README.md              # This file
```

---

## Production Considerations

### 1. Logging & Monitoring
- Add structured logging to ingestion service
- Monitor query performance
- Track constraint violations

### 2. Error Handling
- Implement retry logic for transient failures
- Add error recovery for data ingestion
- Validate data before MERGE operations

### 3. Scalability
- Use batching for large imports (transactions of 1000-5000 records)
- Implement parallel ingestion for independent records
- Monitor memory usage during traversals

### 4. Security
- Use read-only transactions for all queries
- Implement role-based access control
- Audit all write operations
- Never expose Cypher generation to untrusted sources (LLMs)

### 5. Testing
- Unit tests for services (mock repositories)
- Integration tests for repositories (test database)
- Property-based testing for schema invariants

---

## Future Enhancements

1. **Temporal queries**: Track entity state changes over time
2. **Graph algorithms**: PageRank for influence, community detection for networks
3. **Risk scoring**: Automated AML risk assessment
4. **Real-time updates**: Streaming data ingestion
5. **API layer**: REST/GraphQL endpoints for external access
6. **Visualization**: Integration with graph visualization tools

---

## License

Internal use only. This is a production system for tax/AML investigations.

## Contact

For questions or issues, contact the platform team.
