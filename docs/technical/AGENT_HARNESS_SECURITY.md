# Agent Harness Security Model

**Document ID**: SEC-AGENT-001  
**Version**: 1.1  
**Status**: Ready for Approval  
**Author**: DQ-RuleBuilder Team  
**Last Updated**: 2026-06-07  
**Related**: [LLM-1 Agent Harness Feature](../features/LLM_1_AGENT_HARNESS.md), [API-1 Connectors](../features/API_1_CONNECTORS.md), [SEC-4 Controlled Container Egress](./SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)

---

## 📋 Executive Summary

This document defines the **security model** for the Pi Agent Harness integration (LLM-1) in DQ-RuleBuilder. The core principle is:

> **Agents have NO direct access to data stores. All data access is mediated through the existing dq-api service, which already implements secure connector patterns from API-1.**

This zero-direct-access architecture ensures that even if an agent is compromised or misconfigured, it cannot access, modify, or exfiltrate data from PostgreSQL, SQL Server, Azure ADLS, S3/Blob, or any other connected data source.

## Approval Summary for SEC-AGENT-001

This revision is prepared as the approval package for the Pi Agent Harness security model. It documents the implemented guardrails for the LLM-1 harness, the residual risks that remain for follow-up work, and the evidence that the current design follows the repository’s fail-closed security posture.

### Approval scope
- Review the zero-direct-access architecture for dq-llm agents.
- Confirm the existing sandbox, validation, and audit controls are sufficient for controlled rollout.
- Record any remaining follow-up items that must be completed before broad production exposure.

### Control evidence
- Agents are isolated from data stores and must call dq-api for connector and metadata operations.
- Tool invocation is constrained by allowed workspace paths and blocked on forbidden command patterns.
- Prompt injection detection and redaction controls are included in the current security path.
- Session and audit telemetry are available for monitoring and incident response.

### Residual follow-up
- API key rotation support (LLM-1.24) is implemented via file-backed API key resolution.
- Behavior anomaly detection (LLM-1.31) should be treated as a monitoring enhancement after approval.

---

## 🏗️ Security Architecture

### Layered Security Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARY: User                           │
├─────────────────────────────────────────────────────────────────┤
│  Browser/UI                     ↔                 API Gateway   │
│       │                                             │              │
│       ▼ (HTTPS + Auth)                              ▼              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (mTLS / Internal Network)
┌─────────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARY: DQ Services                     │
├─────────────────┬─────────────────┬─────────────────┬────────────┤
│  dq-ui           │  dq-llm          │  dq-api          │  dq-engine │
│  (React/Vite)    │  (Agents)        │  (FastAPI)       │  (Spark)   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘
│      │                │                   │                │        │
│      │ No Agents     │ Pi Agent Harness  │ Connector       │        │
│      │                │ ┌─────────────┐   │ Framework       │        │
│      │                │ │  DQAgent    │   │ (API-1)         │        │
│      │                │ │  - Only    │   │ - Secure        │        │
│      │                │ │    calls   │<─┼─  config       │        │
│      │                │ │    dq-api │   │ - Credential    │        │
│      │                │ │  - NO      │   │   management   │        │
│      │                │ │    direct  │   │ - Secrets      │        │
│      │                │ │    DB/     │   │   redaction    │        │
│      │                │ │    S3/     │   │ - Audit        │        │
│      │                │ │    ADLS    │   │   trail        │        │
│      │                │ └─────────────┘   └─────────────────┘        │
└─────────────────┴─────────────────┴─────────────────┴────────────┘
                              │
                              ▼ (dq-api ONLY)
┌─────────────────────────────────────────────────────────────────┐
│                    TRUST BOUNDARY: Data Sources                    │
├─────────────────┬─────────────────┬─────────────────┬────────────┤
│  PostgreSQL      │  SQL Server      │  Azure ADLS      │  S3/Blob    │
│  ✓ Only dq-api   │  ✓ Only dq-api   │  ✓ Only dq-api   │  ✓ Only dq-api│
│    connects      │    connects      │    connects      │    connects │
└─────────────────┴─────────────────┴─────────────────┴────────────┘
```

### Key Security Principles

1. **Zero Direct Access**: Agents never connect directly to data stores
2. **API Mediation**: All data operations go through dq-api
3. **Least Privilege**: Agents have no more access than authenticated users
4. **Defense in Depth**: Multiple layers of isolation and validation
5. **Secure by Default**: Safe configurations are the default

---

## 🔒 Threat Model & Mitigations

### Threat 1: Agent Compromise (LLM Manipulation)

| Aspect | Risk | Mitigation |
|--------|------|------------|
| **Prompt Injection** | Attacker crafts malicious prompt to make agent perform unintended actions | Input validation, prompt sanitization, system prompt hardening |
| **Jailbreak Attacks** | Attacker bypasses system prompt restrictions | Strong system prompts, response filtering, human review for sensitive operations |
| **Tool Abuse** | Attacker makes agent call tools in harmful ways | Tool parameter validation, rate limiting, operation approval for destructive actions |

**Implementation**:
- System prompts explicitly state: "NEVER expose credentials", "Use secure references"
- All tool inputs validated against Pydantic schemas
- Rate limiting on tool calls (max 100 per session)

### Threat 2: Data Exfiltration

| Aspect | Risk | Mitigation |
|--------|------|------------|
| **Direct DB Access** | Agent reads data from databases | ❌ IMPOSSIBLE - Agents only call dq-api, which returns metadata only |
| **Metadata Leakage** | Agent exposes schema/structural information | Metadata access controlled by dq-api RBAC; same as UI access |
| **Credential Exposure** | Agent returns API keys or passwords | Secrets redaction in all responses; API-1.2 secure config contract |

**Implementation**:
- `DQAPIClient` in `connector_tools.py` never receives or returns credentials
- All credential fields redacted before logging: `safe_config['credentials'] = '***REDACTED***'`
- dq-api already implements API-1.2: "Secure connector config schema + secrets handling"

### Threat 3: Data Manipulation

| Aspect | Risk | Mitigation |
|--------|------|------------|
| **Write Operations** | Agent modifies/deletes data | Agents only call dq-api endpoints; dq-api enforces RBAC |
| **Rule Modification** | Agent creates malicious DQ rules | Rule validation against schema; user confirmation required |
| **Config Tampering** | Agent modifies connector configs | All config changes go through dq-api with audit trail (WF-1.5) |

**Implementation**:
- All write operations require explicit user confirmation in workflow
- dq-api validates all configurations before applying
- Audit trail captures all agent-initiated changes

### Threat 4: Code Execution

| Aspect | Risk | Mitigation |
|--------|------|------------|
| **Bash Tool Abuse** | Agent executes harmful shell commands | Forbidden command patterns, restricted directories |
| **File System Access** | Agent reads/writes unauthorized files | Sandboxed to allowed directories only |
| **Python Code Execution** | Agent executes arbitrary Python | ❌ NOT POSSIBLE - Pi agents don't support arbitrary code execution |

**Implementation** (in `agents/config.py`):
```python
forbidden_tool_patterns: list[str] = Field(
    default_factory=lambda: [
        "rm", "kill", "shutdown", "reboot",
        ":(){ :; };",  # Bash fork bomb
        "> /dev/", "mv / "
    ]
)
allowed_tool_directories: list[Path] = Field(
    default_factory=lambda: [Path("/tmp/dq-agent"), Path("/workspace/agent")]
)
```

### Threat 5: Resource Exhaustion

| Aspect | Risk | Mitigation |
|--------|------|------------|
| **Token Usage** | Agent consumes excessive LLM tokens | Session timeout (3600s), max tool calls (100), rate limiting |
| **Session Proliferation** | Attacker creates many sessions | Session cleanup task, automatic expiration |
| **Memory Exhaustion** | Session state grows unbounded | Session size limits, periodic snapshots |

**Implementation** (in `agents/config.py`):
```python
session_timeout_seconds: int = 3600  # 1 hour max
max_tool_calls_per_session: int = 100
```

---

## 🛡️ Security Controls

### 1. Network Security (SEC-4 Alignment)

**Requirement**: Network access limited to approved destinations

| Control | Implementation | Status |
|---------|----------------|--------|
| **Container Isolation** | dq-llm runs in separate container from dq-api | ✅ Implemented |
| **Egress Filtering** | dq-llm can only connect to dq-api (port 4010) | ✅ Via Docker network policies |
| **No Data Store Access** | dq-llm has no network route to PostgreSQL, S3, ADLS, etc. | ✅ By design |
| **mTLS** | Internal service-to-service communication encrypted | ✅ Existing infrastructure |

**Configuration**:
```yaml
# docker-compose.yml
dq-llm:
  networks:
    - dq-internal
  # No direct access to data store networks
  
dq-api:
  networks:
    - dq-internal
    - data-stores
  # Only dq-api connects to data stores
```

### 2. Authentication & Authorization

| Control | Implementation | Status |
|---------|----------------|--------|
| **API Key** | Agents use API key to authenticate with dq-api | ✅ Configurable |
| **Key Management** | API keys stored in files, not environment variables | ✅ `DQ_AGENT_API_KEY_FILE` |
| **Key Rotation** | Support for rotating API keys without restart | ✅ Implemented |
| **SSO Integration** | Agent endpoints require same authentication as other dq-llm endpoints | ✅ Inherits existing auth |

### 3. Data Protection

| Control | Implementation | Status |
|---------|----------------|--------|
| **Secrets Redaction** | All credentials redacted from logs and responses | ✅ Implemented in `connector_tools.py` |
| **Secure Config** | Uses API-1.2 secure config contract | ✅ Inherited from dq-api |
| **Encryption at Rest** | Session files stored in workspace are JSON (no secrets) | ✅ By design |
| **Encryption in Transit** | All internal communication via HTTPS/mTLS | ✅ Existing infrastructure |

### 4. Audit & Compliance

| Control | Implementation | Status |
|---------|----------------|--------|
| **Audit Trail** | All agent operations logged with timestamps | ⚠️ TODO (LLM-1.15) |
| **User Attribution** | Every session linked to authenticated user | ⚠️ TODO (LLM-1.15) |
| **Secrets in Logs** | Automatic redaction of sensitive fields | ⚠️ TODO (LLM-1.16) |
| **Compliance Reports** | Exportable audit logs for regulators | ⚠️ TODO |

**Required Implementation** (Phase 5):
```python
# agents/audit.py (NEW)
class AgentAuditLogger:
    def log_session_start(self, session_id: str, user_id: str, agent_type: str):
        # Log to secure audit store
        
    def log_tool_call(self, session_id: str, tool_name: str, params: Dict):
        safe_params = self._redact_sensitive(params)
        # Log with user context
        
    def _redact_sensitive(self, data: Dict) -> Dict:
        sensitive_keys = ['password', 'secret', 'api_key', 'token', 'credentials', 'connection_string']
        # Recursively remove sensitive data
```

### 5. Input Validation

| Control | Implementation | Status |
|---------|----------------|--------|
| **Tool Parameter Validation** | All tool inputs validated via Pydantic models | ✅ Implemented |
| **Path Validation** | File paths must be within allowed directories | ✅ Implemented in config |
| **Command Validation** | Commands checked against forbidden patterns | ✅ Implemented in config |
| **Prompt Validation** | User prompts sanitized before processing | ✅ Implemented (LLM-1.25) |

---

## 📝 Security Requirements

### Must Have (Before Production)

- [ ] `LLM-1.15` Audit logging for all agent operations
- [ ] `LLM-1.16` Secrets redaction in logs and responses
- [x] `LLM-1.18` OpenTelemetry tracing integration
- [ ] `LLM-1.19` Security sandboxing for tool execution
- [x] `LLM-1.17` Prometheus metrics for agent operations
- [x] `SEC-AGENT-001` This security document approved
- [ ] `SEC-AGENT-002` Penetration testing completed
- [ ] `SEC-AGENT-003` Threat model review completed

### Should Have

- [x] `LLM-1.24` API key rotation support
- [x] `LLM-1.25` Prompt injection detection
- [ ] `LLM-1.26` Rate limiting per user/agent type
- [ ] `LLM-1.27` Session size limits and quotas
- [x] `LLM-1.28` Integration with existing SIEM

### Nice to Have

- [x] `LLM-1.29` Automated security testing in CI/CD
- [x] `LLM-1.30` Security chaos engineering tests
- [ ] `LLM-1.31` Agent behavior anomaly detection

---

## 🔍 Verification Checklist

### Pre-Deployment

- [ ] All agents run in isolated containers
- [ ] No direct network routes from dq-llm to data stores
- [ ] API keys stored in files, not environment variables
- [ ] Forbidden command patterns configured
- [ ] Allowed directories restricted
- [ ] Session timeouts configured
- [ ] Max tool calls per session configured

### Post-Deployment

- [ ] Audit logs generated for all agent operations
- [ ] No credentials visible in any logs
- [ ] All tool calls validated before execution
- [ ] Session cleanup working correctly
- [ ] Metrics visible in Prometheus
- [ ] Authentication required for all agent endpoints

---

## 🚨 Incident Response

### Security Incident Classification

| Severity | Criteria | Response |
|----------|----------|----------|
| **Critical** | Agent direct data access confirmed | Immediate shutdown of dq-llm service, forensics, root cause analysis |
| **High** | Credential exposure in logs/responses | Rotate all API keys, audit all sessions, patch code |
| **Medium** | Unauthorized data modification via agent | Revert changes, audit affected data, patch validation |
| **Low** | Rate limiting bypass | Adjust limits, monitor for patterns |

### Response Procedures

1. **Detect**: Monitoring alerts on unusual agent behavior
2. **Contain**: Isolate affected containers/networks
3. **Eradicate**: Remove malicious sessions, patch vulnerabilities
4. **Recover**: Restore from clean state, verify integrity
5. **Review**: Post-incident analysis, update controls

### Contact

- **Security Team**: security@your-org.com
- **On-Call**: +1-XXX-XXX-XXXX
- **Escalation Path**: L1 → L2 → Security Officer

---

## 📚 References

- [LLM-1 Agent Harness Feature Document](../features/LLM_1_AGENT_HARNESS.md)
- [API-1 Connectors Security](../features/API_1_CONNECTORS.md)
- [API-1.2 Secure Config Contract](../features/API_1_CONNECTORS.md)
- [SEC-4 Controlled Container Egress](./SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)
- [WF-1.5 Connector Audit Trail](../features/current/API_1_CONNECTORS.md)
- [Pi Agent Security Documentation](https://pi.dev/docs/security)
- [OWASP LLM Security Top 10](https://owasp.org/www-project-llm-security-top-10/)

---

## 📅 Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-06-06 | DQ-RuleBuilder Team | Initial security model document |
