# ODCS + OAS Integration Guide

## Overview

This system uses **two complementary standards** for API-driven data quality:

- **OpenAPI Specification (OAS)** — HTTP API surface contracts
- **Open Data Contract Standard (ODCS)** — Data-level contracts (schemas, quality rules, SLOs, ownership)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              API Gateway (OAS Enforced)             │
│  - Authentication (Keycloak/OIDC)                   │
│  - Rate Limiting & Quotas                           │
│  - Request Validation (OAS schemas)                 │
└─────────────────────────────────────────────────────┘
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
┌─────▼──────┐  ┌────────▼────────┐  ┌──────▼──────┐
│  dq-api    │  │   dq-engine     │  │ dq-profiling│
│            │  │  (validates     │  │             │
│ Serves     │  │   against       │  │ Generates   │
│ ODCS       │  │   ODCS rules)   │  │ suggestions │
│ contracts  │  │                 │  │ from ODCS   │
└────────────┘  └─────────────────┘  └─────────────┘
      │                   │                   │
      └───────────────────┼───────────────────┘
                          │
             ┌────────────▼─────────────┐
             │  PostgreSQL              │
             │  - Rule definitions      │
             │  - ODCS contract refs    │
             │  - Validation results    │
             └──────────────────────────┘
```

## ODCS Contract Storage

Contracts are versioned under `data_sources/contracts/`:

```
data_sources/
├── contracts/
│   ├── demo-azure-customer-blob.odcs.yaml
│   ├── demo-azure-payments-sql.odcs.yaml
│   └── ...

dq-api/
└── server/
  ├── data-contracts.controller.ts
  └── ...
```

## API Endpoints

### List All Contracts

```bash
GET /api/data-contracts

Response:
{
  "success": true,
  "contracts": [
    {
      "data_source_id": "demo-azure-payments-sql",
      "contract_url": "/api/data-contracts/demo-azure-payments-sql",
      "format": "odcs/3.1.0"
    }
  ],
  "count": 1
}
```

### Get Contract (YAML)

```bash
GET /api/data-contracts/demo-azure-payments-sql

Response: (application/x-yaml)
apiVersion: v3.1.0
kind: DataContract
id: urn:dq:contract:demo-azure-payments-sql
name: payments_transaction_ledger
  ...
```

### Get Contract (JSON)

```bash
GET /api/data-contracts/demo-azure-payments-sql?format=json

Response: (application/json)
{
  "api_version": "v3.1.0",
  "kind": "DataContract",
  "id": "urn:dq:contract:demo-azure-payments-sql",
  ...
}
```

### Extract Quality Rules

```bash
GET /api/data-contracts/demo-azure-payments-sql/quality-rules

Response:
{
  "success": true,
  "dataSourceId": "demo-azure-payments-sql",
  "qualitySpec": "checks for payments_ledger:\n  - missing_count(transaction_id) = 0...",
  "slos": {
    "completeness": { "target": "99.95%", ... },
    "validity": { "target": "99.9%", ... }
  },
  "format": "SodaCL"
}
```

## Workflow: Consumer Onboarding

### 1. Discover Available Data Sources

External app queries the catalog:

```bash
curl https://api.example.com/api/data-contracts \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Fetch Data Contract

Get the ODCS contract for the target source:

```bash
curl https://api.example.com/api/data-contracts/demo-azure-payments-sql \
  -H "Authorization: Bearer $TOKEN"
```

Consumer now knows:
- **Schema**: field names, types, constraints
- **Quality SLOs**: expected completeness, validity, freshness
- **Ownership**: who to contact for issues
- **Terms**: usage limitations, PII handling

### 3. Map DQ Rules to ODCS Quality Checks

Your `dq-engine` validates data against ODCS-defined rules:

```python
# dq-engine validates incoming data
contract = fetch_odcs_contract("demo-azure-payments-sql")
rules = parse_sodacl_rules(contract["quality"]["specification"])

for rule in rules:
    result = evaluate_rule(data, rule)
    if not result.passed:
        report_violation(rule, result)
```

### 4. Return ODCS-Compliant Results

Validation results reference the contract:

```json
{
  "dataSourceId": "demo-azure-payments-sql",
  "contractVersion": "1.2.0",
  "validationTimestamp": "2026-03-02T10:30:00Z",
  "results": [
    {
      "check": "Transaction ID completeness",
      "status": "passed",
      "severity": "critical"
    },
    {
      "check": "Currency format validation",
      "status": "failed",
      "severity": "high",
      "failedCount": 4,
      "failureRate": 0.000032
    }
  ],
  "overallStatus": "partial_failure"
}
```

## ODCS ↔ DQ Rule Mapping

| ODCS Quality Dimension | DQ Rule Type | Example |
|------------------------|--------------|---------|
| **Completeness** | `NOT_NULL`, `MISSING_COUNT` | `missing_count(customer_id) = 0` |
| **Uniqueness** | `UNIQUE`, `DUPLICATE_COUNT` | `duplicate_count(transaction_id) = 0` |
| **Validity** | `FORMAT_VALIDATION`, `ENUM` | `invalid_count(currency) = 0` |
| **Accuracy** | `RANGE_CHECK`, `REFERENTIAL_INTEGRITY` | `amount_eur >= 0` |
| **Timeliness** | `FRESHNESS` | `freshness(booking_date) < 1d` |
| **Consistency** | `CROSS_FIELD`, `AGGREGATE` | `amount_eur = amount_usd * exchange_rate` |

## Generating Rules from ODCS Contracts

Your profiling service can auto-generate rules from contracts:

```typescript
// dq-api/server/profiling.service.ts

async generateRulesFromContract(dataSourceId: string): Promise<Rule[]> {
  const contract = await this.fetchODCSContract(dataSourceId)
  const rules: Rule[] = []

  // Parse ODCS quality checks (SodaCL)
  const qualitySpec = contract.quality.specification
  const checks = parseSodaCL(qualitySpec)

  for (const check of checks) {
    const rule = {
      name: check.name,
      description: `Contract-enforced: ${check.description}`,
      expression: convertSodaCLToSQL(check),
      dimension: mapSeverityToDimension(check.severity),
      ruleType: inferRuleType(check),
      source: 'odcs-contract',
      contractVersion: contract.info.version,
    }
    rules.push(rule)
  }

  return rules
}
```

## Publishing Contracts to Gateway

At the API Gateway level:

1. **Contract Registry**: Expose `/data-contracts` at gateway for centralized discovery
2. **OAS + ODCS Links**: Add `x-data-contract` extension to OAS endpoints:

```yaml
# openapi.yaml
paths:
  /rules:
    get:
      summary: List quality rules
      x-data-contract:
        dataSourceId: demo-azure-payments-sql
        contractUrl: /api/data-contracts/demo-azure-payments-sql
```

3. **Validation**: Gateway validates requests using OAS; backend validates data using ODCS

## CI/CD Integration

### Contract Validation in CI

```yaml
# .github/workflows/validate-contracts.yml
name: Validate Data Contracts

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install ODCS validator
        run: npm install -g @openlineage/data-contracts-validator
      
      - name: Validate all contracts
        run: |
          for contract in data_sources/contracts/*.odcs.yaml; do
            echo "Validating $contract"
            odcs-validate "$contract"
          done
```

### Breaking Change Detection

```bash
# Check for breaking changes
odcs-diff main.yaml feature-branch.yaml --fail-on-breaking
```

## External Consumer Example

### Python Client

```python
import requests

class DQContractClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"}
    
    def get_contract(self, data_source_id):
        """Fetch ODCS contract for a data source"""
        url = f"{self.base_url}/api/data-contracts/{data_source_id}"
        response = requests.get(url, headers=self.headers, params={"format": "json"})
        response.raise_for_status()
        return response.json()
    
    def get_quality_expectations(self, data_source_id):
        """Get quality SLOs from contract"""
        contract = self.get_contract(data_source_id)
        return contract.get("quality", {}).get("slos", {})

# Usage
client = DQContractClient("https://api.example.com", token="...")
contract = client.get_contract("demo-azure-payments-sql")

print(f"Schema: {contract['models']['payments_ledger']['fields']}")
print(f"Quality SLOs: {contract['quality']['slos']}")
```

## Best Practices

1. **Version contracts semantically**: Breaking changes = major version bump
2. **Link rules to contracts**: Store `contractId` + `contractVersion` in rule metadata
3. **Monitor SLO compliance**: Track actual vs. target quality metrics
4. **Automate suggestion generation**: Profiling → ODCS contract → DQ rules
5. **Governance**: Require contract approval before production data access
6. **Documentation**: Keep contracts in sync with actual data schema

## Migration Path

### Phase 1: Pilot (Current)
- ✅ ODCS contracts for demo data sources
- ✅ API endpoint to serve contracts
- ✅ Manual rule creation referencing contracts

### Phase 2: Integration
- Auto-generate rules from ODCS `quality.specification`
- Update profiling to suggest contract-aligned rules
- Add contract version tracking to rule metadata

### Phase 3: Gateway
- Publish contracts via API Gateway
- Enforce contract-based access control
- Add contract discovery UI

### Phase 4: Ecosystem
- External apps consume contracts programmatically
- Contract-driven alerting (SLO breaches)
- Self-service contract publishing for data owners

## References

- [ODCS Specification](https://github.com/bitol-io/open-data-contract-standard)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [SodaCL Documentation](https://docs.soda.io/soda-cl/soda-cl-overview.html)
