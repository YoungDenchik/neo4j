# Income Anomaly Detector

A deterministic detection system for identifying suspicious income patterns that may indicate money laundering, bribery, tax evasion, or other financial crimes.

## Overview

The detector analyzes income data stored in Neo4j and flags anomalies based on four detection patterns. It does **not** use LLMs or machine learning — all detection logic is rule-based and transparent.

## Detection Patterns

### 1. Income/Tax Mismatch (`INCOME_TAX_MISMATCH`)

**What it detects:** Records where the accrued income differs from the paid income, or where tax charged differs from tax transferred.

**Why it matters:**
- `income_accrued ≠ income_paid` may indicate unreported income or off-the-books payments
- `tax_charged ≠ tax_transferred` suggests tax evasion or accounting fraud

**Cypher pattern:**
```cypher
MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
WHERE abs(i.income_accrued - i.income_paid) > threshold
   OR abs(i.tax_charged - i.tax_transferred) > threshold
```

**Severity:**
- `MEDIUM` — mismatch detected
- `HIGH` — total unpaid income exceeds 100,000 UAH

---

### 2. Concentrated Income Without Employment (`CONCENTRATED_INCOME_NO_EMPLOYMENT`)

**What it detects:** Large income payments from an organization where the person has no formal relationship (not a director or founder).

**Why it matters:**
- Legitimate large payments usually come from employers or owned companies
- Payments without formal relationship may indicate kickbacks, bribes, or undisclosed consulting
- Extra suspicious if the paying organization is terminated or in liquidation

**Cypher pattern:**
```cypher
MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)-[:PAID_BY]->(o:Organization)
WHERE NOT (p)-[:DIRECTOR_OF]->(o)
  AND NOT (p)-[:FOUNDER_OF]->(o)
WITH o, sum(i.income_paid) as total
WHERE total > threshold
```

**Severity:**
- `HIGH` — large income without employment relationship
- `CRITICAL` — paying organization is terminated (state="3") or in liquidation (state="2")

---

### 3. Unusual Income Categories (`UNUSUAL_INCOME_CATEGORY`)

**What it detects:** High-value income in categories commonly used to disguise illicit payments.

**Suspicious income type codes:**
| Code | Description (Ukrainian) | Why suspicious |
|------|------------------------|----------------|
| `126` | Додаткове благо (Additional benefit) | Vague category, easy to misuse |
| `178` | Подарунки (Gifts) | Classic vehicle for bribes |
| `186` | Інші доходи (Other income) | Catch-all with no oversight |

**Why it matters:**
- These categories have less scrutiny than regular salary
- Large amounts in these categories warrant investigation
- Often used to legitimize payments that would otherwise raise questions

**Cypher pattern:**
```cypher
MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)
WHERE i.income_type_code IN ["126", "178", "186"]
  AND i.income_paid > threshold
```

**Severity:**
- `MEDIUM` — suspicious category income detected
- `HIGH` — total exceeds 200,000 UAH

---

### 4. Income Spikes (`INCOME_SPIKE`)

**What it detects:** Years where income significantly exceeds the person's historical average.

**Why it matters:**
- Sudden income jumps may indicate one-time illicit payments
- Bribes and kickbacks often appear as isolated large payments
- Legitimate income changes (promotions, bonuses) can be verified

**Cypher pattern:**
```cypher
MATCH (p:Person)-[:EARNED_INCOME]->(i:IncomeRecord)
WITH p, i.period_year as year, sum(i.income_paid) as yearly_income
WITH year, yearly_income, avg(yearly_income) as historical_avg
WHERE yearly_income > historical_avg * multiplier
```

**Severity:**
- `MEDIUM` — income 3-5x historical average
- `HIGH` — income >5x historical average

---

## Risk Score Calculation

Each person receives a risk score (0-100) based on detected anomalies:

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
# Scan top 100 persons by income
python run_income_analysis.py

# Scan specific person
python run_income_analysis.py --rnokpp "1234567890"

# Verbose output with anomaly details
python run_income_analysis.py --verbose

# Output as JSON
python run_income_analysis.py --json
```

### Arguments Reference

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--rnokpp` | string | None | Analyze specific person by tax ID |
| `--limit` | int | 100 | Number of persons to scan |
| `--json` | flag | False | Output results as JSON |
| `--verbose`, `-v` | flag | False | Show detailed anomaly information |
| `--min-risk` | float | 0 | Only show persons with risk score >= value |

### Threshold Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--mismatch-threshold` | float | 1,000 | Minimum income/tax difference to flag (UAH) |
| `--concentration-threshold` | float | 100,000 | Minimum income from single source to flag (UAH) |
| `--unusual-category-threshold` | float | 50,000 | Minimum suspicious category income to flag (UAH) |
| `--spike-multiplier` | float | 3.0 | Income must exceed average by this factor |

### Examples

```bash
# Find only high-risk individuals
python run_income_analysis.py --min-risk 50

# Scan 500 persons with stricter thresholds
python run_income_analysis.py --limit 500 --concentration-threshold 200000

# Detailed analysis of specific person, output to file
python run_income_analysis.py --rnokpp "1234567890" --verbose > report.txt

# JSON output for integration with other systems
python run_income_analysis.py --limit 1000 --json > anomalies.json

# Very strict detection (fewer false positives)
python run_income_analysis.py \
  --mismatch-threshold 10000 \
  --concentration-threshold 500000 \
  --unusual-category-threshold 200000 \
  --spike-multiplier 5.0
```

---

## Output Format

### Console Output (Default)

```
================================================================================
RNOKPP          Risk  Anomalies   Total Income Name
--------------------------------------------------------------------------------
1234567890       100%          3      1,500,000 Іванов Петро Сергійович
2345678901        65%          2        850,000 Петренко Марія Іванівна
================================================================================
```

### Verbose Output

```
================================================================================
RNOKPP: 1234567890
Name: Іванов Петро Сергійович
Risk Score: 100/100
Total Income: 1,500,000 UAH
Total Tax Paid: 150,000 UAH
Anomalies Found: 3
--------------------------------------------------------------------------------

🚨 Anomaly #1: [CRITICAL] Large Income Without Employment Relationship
   Code: CONCENTRATED_INCOME_NO_EMPLOYMENT
   Received 500,000 UAH from ТОВ "Рога і Копита" without being director or founder
   Recommendation: Verify the nature of payments. May indicate kickbacks, bribes, or undisclosed employment.

🔴 Anomaly #2: [HIGH] High-Value Income in Suspicious Categories
   Code: UNUSUAL_INCOME_CATEGORY
   Received 200,000 UAH in gifts, bonuses, or 'other' income categories
   Recommendation: Review justification for non-salary payments. Categories commonly used to disguise bribes.
```

### JSON Output

```json
{
  "person_rnokpp": "1234567890",
  "person_name": "Іванов Петро Сергійович",
  "total_income": 1500000.0,
  "total_tax_paid": 150000.0,
  "risk_score": 100.0,
  "anomalies": [
    {
      "code": "CONCENTRATED_INCOME_NO_EMPLOYMENT",
      "severity": "CRITICAL",
      "title": "Large Income Without Employment Relationship",
      "description": "Received 500,000 UAH from ТОВ \"Рога і Копита\" without being director or founder",
      "details": {
        "organization_edrpou": "12345678",
        "organization_name": "ТОВ \"Рога і Копита\"",
        "total_income": 500000.0,
        "is_suspicious_org": true
      },
      "person_rnokpp": "1234567890",
      "recommendation": "Verify the nature of payments..."
    }
  ]
}
```

---

## Graph Data Requirements

The detector requires the following data in Neo4j:

### Required Nodes
- `Person` — with `rnokpp`, `last_name`, `first_name`
- `Organization` — with `edrpou`, `name`, `state`
- `IncomeRecord` — with `income_accrued`, `income_paid`, `tax_charged`, `tax_transferred`, `income_type_code`, `period_year`

### Required Relationships
- `(Person)-[:EARNED_INCOME]->(IncomeRecord)`
- `(IncomeRecord)-[:PAID_BY]->(Organization)`
- `(Person)-[:DIRECTOR_OF]->(Organization)` (optional, for employment check)
- `(Person)-[:FOUNDER_OF]->(Organization)` (optional, for ownership check)

---

## Programmatic Usage

```python
from services.income_anomaly_detector import IncomeAnomalyDetector
from core.neo4j_driver import init_driver, close_driver

init_driver()

detector = IncomeAnomalyDetector(
    concentration_threshold=200_000,
    spike_multiplier=4.0,
)

# Analyze single person
analysis = detector.analyze_person("1234567890")
print(f"Risk score: {analysis.risk_score}")
for anomaly in analysis.anomalies:
    print(f"  [{anomaly.severity}] {anomaly.title}")

# Scan all persons
results = detector.scan_all_persons(limit=500)
high_risk = [r for r in results if r.risk_score >= 50]

close_driver()
```

---

## Limitations

1. **No ML/AI** — Detection is rule-based. Complex fraud patterns may require additional analysis.
2. **Threshold-dependent** — Results vary based on threshold settings. Tune for your data.
3. **Data quality** — Relies on accurate income_type_code classification in source data.
4. **Point-in-time** — Analyzes current snapshot, not historical changes.

## Future Enhancements

- Temporal pattern analysis (payment timing correlations)
- Network-based detection (co-director clusters receiving similar payments)
- Integration with external watchlists
- Automated threshold tuning based on population statistics
