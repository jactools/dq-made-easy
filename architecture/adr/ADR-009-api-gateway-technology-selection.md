# ADR-009: API Gateway Technology Selection

**Status**: ✅ Implemented (Kong Gateway)  
**Date**: 2026-03-02

### Context
Need API gateway for multi-consumer access, rate limiting, authentication delegation, and observability. Must integrate with Azure environment while maintaining deployment flexibility.

### Options Evaluated

| Factor | Kong Gateway | Azure APIM | AWS API Gateway |
|--------|-------------|------------|-----------------|
| **Cost** | Free (OSS) / $$ (Enterprise) | $$$$ High | $$$ Pay-per-request |
| **Performance** | Excellent (NGINX) | Good | Good |
| **Plugins** | 1000+ plugins | Limited | Moderate |
| **Deployment** | Any (Docker/K8s/VM) | Azure only | AWS only |
| **Lock-in** | None | High | High |
| **Learning Curve** | Moderate | Steep | Moderate |
| **Azure Integration** | Via plugins | Native | N/A |

### Decision
**Selected: Kong Gateway (Open Source)**

**Rationale**:
1. **Cost-Effective**: Open source option meets current needs, can upgrade to Enterprise later
2. **Performance**: NGINX-based, handles 100k+ requests/sec
3. **Flexibility**: Not locked to Azure, can deploy on AKS, Container Instances, or VMs
4. **Plugin Ecosystem**: Rich plugin library (CORS, JWT, rate limiting, Prometheus, etc.)
5. **Kubernetes-Native**: Kong Ingress Controller for AKS deployment
6. **Community**: Large, active open source community

**Implementation Plan**:
- Phase 1 (✅ Done): Documentation and Docker Compose setup
- Phase 2 (✅ Done): Configure routes, CORS, rate limiting
- Phase 3 (Pending): Keycloak OIDC integration for JWT validation
- Phase 4 (Pending): Production deployment on Azure AKS

**See**: [KONG_GATEWAY_SETUP.md](./KONG_GATEWAY_SETUP.md) for complete implementation guide.

### Consequences
**Positive**:
- No vendor lock-in - can switch cloud providers
- Free to start, paid upgrade path available
- Excellent performance characteristics
- Proven at scale (used by Fortune 500s)
- Active development and security updates
- Can self-host or use Kong Cloud

**Negative**:
- Requires separate infrastructure (database, Redis)
- Manual Azure integration (vs. native APIM)
- Team must learn Kong administration
- Need to manage Kong upgrades

### Configuration Summary
- **Database**: PostgreSQL (same as DQ API)
- **Rate Limiting**: Redis (Azure Cache for Redis in production)
- **TLS**: Let's Encrypt or Azure Key Vault certificates
- **Monitoring**: Prometheus metrics → Azure Monitor or Grafana
- **Admin UI**: Kong Manager

---

