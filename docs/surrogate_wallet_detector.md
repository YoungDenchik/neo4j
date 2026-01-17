# Surrogate Wallet Detector (Гаманець оточення)

A deterministic detection system for identifying patterns where officials hide assets by registering them in the names of low-income proxies while maintaining control through power of attorney.

## Overview

The detector analyzes ownership and power of attorney relationships in Neo4j to find cases where:
- A low-income person owns valuable assets
- An official/PEP has power of attorney for those assets
- This suggests the official is the beneficial owner but hides ownership

This is a common corruption pattern where officials avoid asset declarations by using trusted proxies (drivers, guards, distant relatives).

## Detection Patterns

### 1. PoA Asset Proxy (`POA_ASSET_PROXY`)

**What it detects:** Official has power of attorney for an asset that is legally owned by a low-income person.

**Why it matters:**
- If proxy's income cannot explain asset acquisition, the official may be the true owner
- PoA gives the official effective control without legal ownership
- Common pattern for hiding luxury vehicles and real estate

**Cypher pattern:**
```cypher
MATCH (official:Person {rnokpp: $rnokpp})
MATCH (poa:PowerOfAttorney)-[:HAS_REPRESENTATIVE]->(official)
MATCH (poa)-[:HAS_PROPERTY]->(asset:Property)
MATCH (proxy:Person)-[:OWNS]->(asset)
WHERE proxy.rnokpp <> official.rnokpp

OPTIONAL MATCH (proxy)-[:EARNED_INCOME]->(inc:IncomeRecord)
WITH official, poa, asset, proxy, sum(inc.income_paid) as proxy_total_income
WHERE proxy_total_income < $threshold OR proxy_total_income IS NULL
```

**Severity:**
- `HIGH` — low-income proxy owns asset with PoA to official
- `CRITICAL` — proxy has zero recorded income

---

### 2. Connected Low-Income Luxury Owner (`CONNECTED_LOW_INCOME_LUXURY_OWNER`)

**What it detects:** Persons who received PoA from an official and own multiple assets despite low income.

**Why it matters:**
- Official giving PoA to someone creates a trust relationship
- If the recipient owns assets disproportionate to their income, they may be holding them for the official
- Multiple assets strengthen the suspicion

**Cypher pattern:**
```cypher
MATCH (official:Person {rnokpp: $rnokpp})
MATCH (poa:PowerOfAttorney)-[:HAS_GRANTOR]->(official)
MATCH (poa)-[:HAS_REPRESENTATIVE]->(proxy:Person)
MATCH (proxy)-[:OWNS]->(asset:Property)

OPTIONAL MATCH (proxy)-[:EARNED_INCOME]->(inc:IncomeRecord)
WITH official, proxy, sum(inc.income_paid) as proxy_income, count(asset) as asset_count
WHERE proxy_income < $threshold AND asset_count > 0
```

**Severity:**
- `HIGH` — PoA recipient with low income owns assets
- `CRITICAL` — PoA recipient owns more than 2 assets

---

### 3. Suspicious Proxy Asset (`SUSPICIOUS_PROXY_ASSET`)

**What it detects:** Scanning from proxy perspective — finds all low-income asset owners with PoA links to officials.

**Why it matters:**
- Alternative detection approach that starts from potential proxies
- Catches patterns where official is not the PoA grantor but still has representative rights
- Useful for broad screening

**Cypher pattern:**
```cypher
MATCH (proxy:Person)-[:OWNS]->(asset:Property)
OPTIONAL MATCH (proxy)-[:EARNED_INCOME]->(inc:IncomeRecord)
WITH proxy, asset, sum(inc.income_paid) as total_income
WHERE total_income < $threshold OR total_income IS NULL

MATCH (poa:PowerOfAttorney)-[:HAS_PROPERTY]->(asset)
MATCH (poa)-[:HAS_REPRESENTATIVE]->(official:Person)
WHERE official.rnokpp <> proxy.rnokpp
```

**Severity:**
- `HIGH` — low-income owner with PoA link to official

---

## Risk Score Calculation

Each official receives a risk score (0-100) based on detected anomalies:

| Severity | Points |
|----------|--------|
| LOW | 10 |
| MEDIUM | 25 |
| HIGH | 40 |
| CRITICAL | 60 |

Scores are summed and capped at 100.

---

## CLI Usage

### Basic Commands

```bash
# Scan all officials for surrogate wallet patterns
python run_surrogate_wallet_analysis.py

# Analyze specific official
python run_surrogate_wallet_analysis.py --rnokpp "1234567890"

# Scan from proxy perspective (find suspicious asset owners)
python run_surrogate_wallet_analysis.py --scan-proxies

# Verbose output with anomaly details
python run_surrogate_wallet_analysis.py --verbose

# Output as JSON
python run_surrogate_wallet_analysis.py --json
```

### Arguments Reference

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--rnokpp` | string | None | Analyze specific official by tax ID |
| `--limit` | int | 100 | Number of officials to scan |
| `--scan-proxies` | flag | False | Scan from proxy perspective |
| `--json` | flag | False | Output results as JSON |
| `--verbose`, `-v` | flag | False | Show detailed anomaly information |
| `--min-risk` | float | 0 | Only show officials with risk score >= value |

### Threshold Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--low-income-threshold` | float | 100,000 | Annual income below this is considered "low" (UAH) |

### Examples

```bash
# Find only high-risk officials
python run_surrogate_wallet_analysis.py --min-risk 50

# Scan with stricter income threshold
python run_surrogate_wallet_analysis.py --low-income-threshold 50000

# Find suspicious proxies and output to file
python run_surrogate_wallet_analysis.py --scan-proxies --verbose > proxies_report.txt

# JSON output for integration
python run_surrogate_wallet_analysis.py --limit 500 --json > surrogate_wallets.json
```

---

## Output Format

### Console Output (Default)

```
================================================================================
RNOKPP          Risk  Anomalies Name
--------------------------------------------------------------------------------
1234567890       100%          3 Іванов Петро Сергійович
2345678901        65%          2 Петренко Марія Іванівна
================================================================================
```

### Verbose Output

```
================================================================================
Official RNOKPP: 1234567890
Name: Іванов Петро Сергійович
Risk Score: 100/100
Anomalies Found: 2
--------------------------------------------------------------------------------

🚨 Anomaly #1: [CRITICAL] Power of Attorney for Asset Owned by Low-Income Proxy
   Code: POA_ASSET_PROXY
   Official has PoA for VEHICLE owned by Сидоренко Іван Петрович whose total income is 0 UAH
   Proxy RNOKPP: 9876543210
   Recommendation: Investigate the relationship between official and proxy...

🔴 Anomaly #2: [HIGH] PoA Recipient with Low Income Owns Multiple Assets
   Code: CONNECTED_LOW_INCOME_LUXURY_OWNER
   Official gave PoA to Коваленко Марія Степанівна who has 45,000 UAH income but owns 3 asset(s)
   Proxy RNOKPP: 8765432109
   Recommendation: Verify legitimate source of proxy's assets...
```

---

## Graph Data Requirements

The detector requires the following data in Neo4j:

### Required Nodes
- `Person` — with `rnokpp`, `last_name`, `first_name`
- `Property` — with `property_id`, `property_type`, `description`
- `PowerOfAttorney` — with `poa_id`, `attested_date`
- `IncomeRecord` — with `income_paid`

### Required Relationships
- `(Person)-[:OWNS]->(Property)`
- `(PowerOfAttorney)-[:HAS_GRANTOR]->(Person)`
- `(PowerOfAttorney)-[:HAS_REPRESENTATIVE]->(Person)`
- `(PowerOfAttorney)-[:HAS_PROPERTY]->(Property)`
- `(Person)-[:EARNED_INCOME]->(IncomeRecord)`

---

## Programmatic Usage

```python
from services.surrogate_wallet_detector import SurrogateWalletDetector
from core.neo4j_driver import init_driver, close_driver

init_driver()

detector = SurrogateWalletDetector(
    low_income_threshold=50_000,
)

# Analyze single official
analysis = detector.analyze_official("1234567890")
print(f"Risk score: {analysis.risk_score}")
for anomaly in analysis.anomalies:
    print(f"  [{anomaly.severity}] {anomaly.title}")
    print(f"    Proxy: {anomaly.proxy_rnokpp}")

# Scan all officials
results = detector.scan_all_officials(limit=500)
high_risk = [r for r in results if r.risk_score >= 50]

# Alternative: scan from proxy perspective
proxy_results = detector.scan_all_proxies(limit=1000)

close_driver()
```

---

## Limitations

1. **Income data completeness** — If proxy's income is not in the system, they may falsely appear as "zero income"
2. **Legitimate PoAs** — Some PoAs to non-family members are legitimate (e.g., to lawyers, business partners)
3. **Asset valuation** — Current implementation doesn't distinguish luxury vs. regular assets
4. **Indirect ownership** — Cannot detect multi-hop proxy chains (A → B → C)

## Future Enhancements

- Asset valuation integration (distinguish luxury cars from economy vehicles)
- Multi-hop proxy chain detection
- Cross-reference with declared assets in NAZK declarations
- Temporal analysis (when was asset acquired vs. when was PoA issued)
