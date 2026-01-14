# Graph Schema Design: Tax/AML Knowledge Graph

## Design Philosophy

This schema follows graph-first principles:
- **Nodes** = Real-world entities (nouns): Person, Organization, Property, etc.
- **Relationships** = Facts and actions (verbs): RECEIVED_INCOME_FROM, DIRECTOR_OF, etc.
- **Each relationship = exactly one fact** with temporal/contextual properties
- **Stable unique identifiers** for all entities (RNOKPP for persons, EDRPOU for orgs)
- **No dynamic schema** - all node labels and relationship types explicitly defined

## Node Types

### 1. Person
**Represents:** Natural persons (taxpayers, directors, family members)
**Identity:** `rnokpp` (Ukrainian tax ID)
**Properties:**
- rnokpp: string (unique, required)
- last_name: string
- first_name: string
- middle_name: string
- date_birth: date (ISO format)

**Why:** Core entity in tax/AML investigations. RNOKPP is the stable government-issued identifier.

### 2. Organization
**Represents:** Legal entities (companies, government agencies, tax agents)
**Identity:** `edrpou` (Ukrainian company registration code)
**Properties:**
- edrpou: string (unique, required)
- name: string (primary display name)
- short_name: string (optional)
- state: string (e.g., "зареєстровано", "припинено")
- state_code: string (e.g., "1", "3")
- olf_code: string (organizational-legal form code)
- olf_name: string (e.g., "ТОВАРИСТВО З ОБМЕЖЕНОЮ ВІДПОВІДАЛЬНІСТЮ")
- authorised_capital: float (optional)
- registration_date: date (optional)

**Why:** Organizations are distinct from persons. EDRPOU ensures no confusion between individuals and entities.

### 3. IncomeRecord
**Represents:** Individual income payment event (fact)
**Identity:** Synthetic `income_id` (generated from person+taxagent+period+type)
**Properties:**
- income_id: string (unique, required)
- income_accrued: float
- income_paid: float
- tax_charged: float
- tax_transferred: float
- income_type_code: string (e.g., "101", "150", "195")
- income_type_description: string (e.g., "Заробітна плата")
- period_quarter_month: string
- period_year: int
- result_income: int

**Why:** Income is a FACT that connects Person and Organization. Making it a node allows:
- Querying temporal income patterns
- Aggregating income sources
- Tracking tax compliance
- Each income payment is independently auditable

### 4. Property
**Represents:** Real estate or vehicles
**Identity:** Synthetic `property_id` (from source data)
**Properties:**
- property_id: string (unique, required)
- property_type: string (e.g., "REAL_ESTATE", "VEHICLE")
- description: string
- government_reg_number: string (for vehicles)
- serial_number: string (VIN for vehicles)
- address: string (for real estate)
- area: float (for real estate, sq.m.)

**Why:** Properties are key in AML - unexplained ownership is a red flag.

### 5. Request
**Represents:** Investigation request document
**Identity:** `request_id` (from IDrequest field)
**Properties:**
- request_id: string (unique, required)
- basis_request: string (e.g., "6161-ТІТ")
- application_number: string
- application_date: datetime
- period_begin_month: int
- period_begin_year: int
- period_end_month: int
- period_end_year: int

**Why:** Tracks provenance - which investigations triggered which data collection.

### 6. Executor
**Represents:** Person who created the investigation request
**Identity:** `executor_rnokpp`
**Properties:**
- executor_rnokpp: string (unique, required)
- executor_edrpou: string (organization code)
- full_name: string

**Why:** Audit trail for investigations.

### 7. PowerOfAttorney
**Represents:** Legal power of attorney document
**Identity:** Synthetic `poa_id`
**Properties:**
- poa_id: string (unique, required)
- notarial_reg_number: string
- attested_date: datetime
- finished_date: datetime
- witness_name: string

**Why:** Shows control relationships - who can act on behalf of whom.

## Relationship Types

### Person → Organization

1. **DIRECTOR_OF**
   - **Meaning:** Person is a director/head of organization
   - **Properties:** role_text (e.g., "керівник")
   - **Cardinality:** Many-to-many
   - **Source:** Company registry "heads" field

2. **FOUNDER_OF**
   - **Meaning:** Person is a founder/shareholder of organization
   - **Properties:**
     - capital: float (investment amount)
     - role_text: string (e.g., "засновник")
   - **Cardinality:** Many-to-many
   - **Source:** Company registry "founders" field

### Person → Person

3. **CHILD_OF**
   - **Meaning:** Person is a child of another person
   - **Properties:** None (biological relationship)
   - **Cardinality:** Many-to-two (each person has max 2 parents)
   - **Source:** Birth certificate data

4. **SPOUSE_OF**
   - **Meaning:** Person is married to another person
   - **Properties:** marriage_date (optional)
   - **Cardinality:** One-to-one (at a given time)
   - **Source:** Marriage records

### IncomeRecord relationships

5. **EARNED_INCOME** (Person → IncomeRecord)
   - **Meaning:** Person earned this specific income
   - **Properties:** None (all data in IncomeRecord node)
   - **Cardinality:** One-to-many

6. **PAID_BY** (IncomeRecord → Organization)
   - **Meaning:** This income was paid by organization
   - **Properties:** None
   - **Cardinality:** Many-to-one

**Why split into two relationships?**
- Allows efficient queries: "all income for person X" or "all payments by org Y"
- Clear directionality of money flow
- IncomeRecord is the immutable fact connecting them

### Property relationships

7. **OWNS** (Person → Property)
   - **Meaning:** Person owns this property
   - **Properties:**
     - ownership_type: string (optional)
     - since_date: date (optional)
   - **Cardinality:** Many-to-many

8. **GRANTOR_OF** (Person → PowerOfAttorney)
   - **Meaning:** Person granted power of attorney
   - **Properties:** None
   - **Cardinality:** One-to-many

9. **REPRESENTATIVE_OF** (Person → PowerOfAttorney)
   - **Meaning:** Person received power of attorney
   - **Properties:** None
   - **Cardinality:** One-to-many

10. **AUTHORIZES_PROPERTY** (PowerOfAttorney → Property)
    - **Meaning:** Power of attorney covers this property
    - **Properties:** None
    - **Cardinality:** One-to-many

### Investigation relationships

11. **CREATED_REQUEST** (Executor → Request)
    - **Meaning:** Executor created this request
    - **Properties:** None
    - **Cardinality:** One-to-many

12. **SUBJECT_OF** (Request → Person)
    - **Meaning:** Request investigates this person
    - **Properties:** None
    - **Cardinality:** One-to-one (each request targets one person)

## Constraints & Indexes

### Uniqueness Constraints
```cypher
CREATE CONSTRAINT person_rnokpp IF NOT EXISTS FOR (p:Person) REQUIRE p.rnokpp IS UNIQUE;
CREATE CONSTRAINT org_edrpou IF NOT EXISTS FOR (o:Organization) REQUIRE o.edrpou IS UNIQUE;
CREATE CONSTRAINT income_id IF NOT EXISTS FOR (i:IncomeRecord) REQUIRE i.income_id IS UNIQUE;
CREATE CONSTRAINT property_id IF NOT EXISTS FOR (p:Property) REQUIRE p.property_id IS UNIQUE;
CREATE CONSTRAINT request_id IF NOT EXISTS FOR (r:Request) REQUIRE r.request_id IS UNIQUE;
CREATE CONSTRAINT executor_rnokpp IF NOT EXISTS FOR (e:Executor) REQUIRE e.executor_rnokpp IS UNIQUE;
CREATE CONSTRAINT poa_id IF NOT EXISTS FOR (p:PowerOfAttorney) REQUIRE p.poa_id IS UNIQUE;
```

### Indexes (for query performance)
```cypher
CREATE INDEX person_name IF NOT EXISTS FOR (p:Person) ON (p.last_name, p.first_name);
CREATE INDEX person_birth IF NOT EXISTS FOR (p:Person) ON (p.date_birth);
CREATE INDEX org_name IF NOT EXISTS FOR (o:Organization) ON (o.name);
CREATE INDEX income_year IF NOT EXISTS FOR (i:IncomeRecord) ON (i.period_year);
CREATE INDEX request_date IF NOT EXISTS FOR (r:Request) ON (r.application_date);
```

## Design Decisions

### Why IncomeRecord as Node (not relationship)?
- **Pro:** Each payment is a queryable fact with many attributes
- **Pro:** Enables temporal queries: "show income trend over time"
- **Pro:** Prevents relationship property explosion
- **Alternative considered:** Person-[:RECEIVED_INCOME]->Organization would create hundreds of relationships between same nodes

### Why separate Executor from Person?
- **Executors are investigators**, not subjects - different domain role
- **Prevents query confusion** - clear separation of concerns
- **Could merge later** if needed, but separation is safer initially

### Why synthetic IDs for some entities?
- **IncomeRecord:** No natural key in source data; hash of (rnokpp + edrpou + period + type) ensures uniqueness
- **Property:** Source data may not have stable IDs; generate from content
- **PowerOfAttorney:** Notarial reg number + date creates stable ID

### Relationship direction conventions
- **Money flow:** Person ← EARNED_INCOME ← IncomeRecord ← PAID_BY ← Organization
- **Ownership:** Person → OWNS → Property
- **Corporate roles:** Person → DIRECTOR_OF/FOUNDER_OF → Organization
- **Family:** Person → CHILD_OF → Person (parent)

## Query Examples

### Find all income sources for a person
```cypher
MATCH (p:Person {rnokpp: $rnokpp})-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
RETURN o.name, sum(i.income_paid) as total_paid, collect(i.period_year) as years
ORDER BY total_paid DESC
```

### Find undeclared beneficial owners
```cypher
MATCH (p:Person)-[:FOUNDER_OF]->(o:Organization)-[:FOUNDER_OF]-(other:Person)
WHERE NOT (p)-[:DIRECTOR_OF]->(o)
RETURN p, o, other
```

### Detect income mismatch
```cypher
MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)
WHERE i.income_accrued <> i.income_paid
RETURN p.rnokpp, p.last_name, sum(i.income_accrued - i.income_paid) as unpaid
```

### Family wealth consolidation
```cypher
MATCH (p:Person)-[:CHILD_OF|SPOUSE_OF*1..2]-(relative:Person)
MATCH (relative)-[:OWNS]->(prop:Property)
RETURN p.last_name as family, count(prop) as properties, collect(prop.description) as assets
```
