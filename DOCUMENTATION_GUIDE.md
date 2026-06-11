# Documentation Guide

This project has separate documentation for different audiences. Choose the right guide for your needs:

## 📖 For End Users

**Start here:** [RELEASE_NOTES_USER.md](./RELEASE_NOTES_USER.md)

Contains:
- ✅ Feature overview and benefits
- ✅ Step-by-step usage instructions
- ✅ Tips and best practices
- ✅ FAQ and troubleshooting
- ✅ Common workflows

**Perfect for:** Learning how to use new features, understanding capabilities, getting started.

### Quick Navigation
- **What's new in v0.3.3?** → [Development Mode Icon Fix](./RELEASE_NOTES_USER.md#v033--development-mode-icon-fix-march-13-2026)
- **What's new in v0.3.2?** → [SSO Reliability & Auth Stabilization](./RELEASE_NOTES_USER.md#v032--sso-reliability--auth-stabilization-march-11-2026)
- **What's new in v0.3.0?** → [Kong Gateway, Reliability & UX Fixes](./RELEASE_NOTES_USER.md#v030--kong-gateway-reliability--ux-fixes-march-3-2026)
- **How do I use suggestions?** → [How to Use](./RELEASE_NOTES_USER.md#-how-to-use-rule-suggestions)
- **I have a question** → [FAQ](./RELEASE_NOTES_USER.md#-faq)

---

## 🔧 For Developers & Admins

**Start here:** [TECHNICAL.md](./TECHNICAL.md)

Contains:
- ✅ Complete API reference
- ✅ Database schema and queries
- ✅ Backend architecture and services
- ✅ Job queue setup (Bull/Redis)
- ✅ Deployment and configuration
- ✅ Monitoring and troubleshooting
- ✅ Performance tuning guides

**Perfect for:** Deployment, integration, extension, debugging, monitoring.

### Quick Navigation
- **What changed in v0.3.3?** → [Changelog](./TECHNICAL.md#v033-march-13-2026)
- **What changed in v0.3.2?** → [Changelog](./TECHNICAL.md#v032-march-11-2026)
- **API endpoints?** → [API Reference](./TECHNICAL.md#api-reference)
- **Database schema?** → [Database Schema](./TECHNICAL.md#database-schema)
- **How to deploy?** → [Deployment](./TECHNICAL.md#deployment)
- **Rate limiting config?** → [Configuration](./TECHNICAL.md#configuration)
- **Something not working?** → [Troubleshooting](./TECHNICAL.md#troubleshooting)

---

## 🎨 In-App Documentation

The application includes a built-in **Release Notes** page:

1. Open the app in your browser
2. Click **"Release Notes"** in the sidebar (bottom area)
3. Expand release versions to see features and changes
4. Perfect for discovering new capabilities

---

## 📚 Other Resources

| Resource | Purpose |
|----------|---------|
| [README.md](./README.md) | Quick start & overview |
| [docs/features/README.md](./docs/features/README.md) | Feature index and navigation |
| [src/hooks/useSuggestions.ts](./dq-ui/src/hooks/useSuggestions.ts) | React hook documentation |
| [src/types/rules.ts](./dq-ui/src/types/rules.ts) | TypeScript type definitions |

### API Specifications (OpenAPI 3.0)

Interactive API documentation via **Swagger UI**:
- **Local Access**: http://localhost:4001/api-docs (or http://localhost:8000/api-docs via Kong Gateway)
- **What it includes**: All 60+ endpoints with request/response schemas, organized by tags
- **Try it out**: Test endpoints directly from browser with authentication support
- **Export**: Generate client SDKs from OpenAPI JSON spec

**Documentation**: [KONG_QUICKSTART.md → API Specifications](./dq-api/KONG_QUICKSTART.md#api-specifications-openapi-30)

**Key endpoint groups**:
- Rules Management (`/v1/rules`)
- Workspaces (`/v1/workspaces`)
- Approvals (`/v1/approvals`)
- Data Catalog (`/v1/data-catalog/*`)
- Profiling (`/v1/suggestions/*`)
- Authentication (`/v1/login`, `/v1/logout`)

### Data Contracts (ODCS 3.1.0)

Vendor-neutral **Open Data Contract Standard** support:
- **Access**: `/v1/data-contracts` endpoint
- **Format**: YAML and JSON support
- **What it includes**: Schema definitions, quality rules, SLAs, lineage information
- **Standards**: Compliant with ODCS 3.1.0 + SodaCL for quality specifications
- **Use cases**: API client generation, documentation, CI/CD validation, cross-team collaboration

**Documentation**: [KONG_QUICKSTART.md → Data Contracts](./dq-api/KONG_QUICKSTART.md#data-contracts-odcs-310)

**Example endpoints**:
```bash
# List all contracts
curl http://localhost:8000/v1/data-contracts

# Get specific contract (YAML)
curl http://localhost:8000/v1/data-contracts/customer_data

# Extract quality rules
curl http://localhost:8000/v1/data-contracts/customer_data/quality-rules
```

---

## 🎯 Choose Your Path

### "I want to..."

**...use the new suggestions feature**
→ Read [RELEASE_NOTES_USER.md](./RELEASE_NOTES_USER.md) → Step-by-step instructions section

**...deploy the application**
→ Read [TECHNICAL.md](./TECHNICAL.md) → Deployment section

**...integrate suggestions with my app**
→ Read [TECHNICAL.md](./TECHNICAL.md) → API Reference section

**...explore the API specification**
→ Visit http://localhost:4001/api-docs for interactive Swagger UI
→ Read [API Specifications section](#api-specifications-openapi-30) above

**...work with data contracts**
→ Access `/v1/data-contracts` endpoint for ODCS 3.1.0 contracts
→ Read [Data Contracts section](#data-contracts-odcs-310) above

**...understand the architecture**
→ Read [TECHNICAL.md](./TECHNICAL.md) → Architecture section

**...troubleshoot an issue**
→ [RELEASE_NOTES_USER.md](./RELEASE_NOTES_USER.md) for user issues
→ [TECHNICAL.md](./TECHNICAL.md) for technical issues

**...report feedback**
→ [RELEASE_NOTES_USER.md](./RELEASE_NOTES_USER.md) → Feedback section

---

## 📋 Document Structure

```
Documentation/
├── RELEASE_NOTES_USER.md              ← User features & usage (165 lines)
├── TECHNICAL.md                       ← Technical details & API (584 lines)
├── README.md                          ← Quick start & overview
├── docs/features/README.md            ← Feature index
├── DOCUMENTATION_GUIDE.md             ← This file
└── dq-api/
    ├── KONG_GATEWAY_SETUP.md          ← Kong Gateway implementation guide
    ├── KONG_QUICKSTART.md             ← Kong 5-minute quick start
    ├── API_GATEWAY_DESIGN.md          ← Gateway architecture design
    └── V1_MIGRATION_BIG_BANG.md       ← API v1 migration guide
└── architecture/
    └── ARCHITECTURAL_DECISIONS.md     ← ADRs for API gateway & quick wins
```

---

## ❓ Still Need Help?

1. **Check the FAQ** in [RELEASE_NOTES_USER.md](./RELEASE_NOTES_USER.md#-faq)
2. **Search the docs** for keywords (Ctrl+F / Cmd+F)
3. **Read the in-app Release Notes** (sidebar)
4. **Contact your administrator** for support

---

## 🚀 Quick Links

| For Users | For Developers |
|-----------|----------------|
| [Feature Overview](./RELEASE_NOTES_USER.md#-whats-new) | [API Reference](./TECHNICAL.md#api-reference) |
| [Usage Instructions](./RELEASE_NOTES_USER.md#-how-to-use-rule-suggestions) | [Database Schema](./TECHNICAL.md#database-schema) |
| [Tips & Tricks](./RELEASE_NOTES_USER.md#-tips--tricks) | [Deployment](./TECHNICAL.md#deployment) |
| [FAQ](./RELEASE_NOTES_USER.md#-faq) | [Troubleshooting](./TECHNICAL.md#troubleshooting) |
| [Settings Help](./RELEASE_NOTES_USER.md#%EF%B8%8F-settings) | [Configuration](./TECHNICAL.md#configuration) |
| | [API Specs (OpenAPI)](./dq-api/KONG_QUICKSTART.md#api-specifications-openapi-30) |
| | [Data Contracts (ODCS)](./dq-api/KONG_QUICKSTART.md#data-contracts-odcs-230) |

---

**Last Updated:** March 3, 2026  
**Version:** 0.3.0 (Kong Gateway stabilization + login/data reliability fixes)
