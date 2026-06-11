# API Versioning - Big Bang Migration to /v1/*

**Status**: ✅ Completed  
**Date**: 2026-03-02  
**Decision**: Big Bang (Option C)

## Summary

All API endpoints have been migrated to `/v1/*` in a single changeover. No gradual migration period - clean break.

## What Changed

### 1. Controller Route Prefixes

#### Before:
```typescript
@Controller()              // Rules, approvals, etc. at root
@Controller('api/suggestions')
@Controller('api/data-contracts')
@Controller('v1')          // Health endpoints only
```

#### After:
```typescript
@Controller('v1')          // Rules, approvals, workspaces, users, etc.
@Controller('v1/suggestions')
@Controller('v1/data-contracts')
@Controller('v1')          // Health endpoints (unchanged)
```

### 2. URL Mapping

All endpoints now start with `/v1/`:

| Endpoint Category | Old Path | New Path |
|------------------|----------|----------|
| **Rules** | `/rules` | `/v1/rules` |
| **Workspaces** | `/workspaces` | `/v1/workspaces` |
| **Approvals** | `/approvals` | `/v1/approvals` |
| **Users** | `/users` | `/v1/users` |
| **Attributes** | `/attributes` | `/v1/attributes` |
| **Data Catalog** | `/data-products` | `/v1/data-products` |
| **Testing** | `/rules/:id/test` | `/v1/rules/:id/test` |
| **Authentication** | `/login` | `/v1/login` |
| **Configuration** | `/app-config` | `/v1/app-config` |
| **Suggestions** | `/api/suggestions/*` | `/v1/suggestions/*` |
| **Data Contracts** | `/api/data-contracts/*` | `/v1/data-contracts/*` |
| **Health** | `/v1/health` | `/v1/health` (unchanged) |

### 3. Complete Endpoint List

#### Rules API (`/v1/rules`)
- `GET /v1/rules` - List all rules
- `GET /v1/rules/:id` - Get rule by ID
- `POST /v1/rules` - Create new rule
- `PUT /v1/rules/:id` - Update rule
- `DELETE /v1/rules/:id` - Delete rule
- `POST /v1/rules/:id/test` - Log test action
- `POST /v1/rules/:id/test-with-data` - Test with provided data
- `POST /v1/rules/:id/test-with-generated-data` - Test with generated data
- `GET /v1/test-proofs/:ruleId` - Get test proofs

#### Workspaces API (`/v1/workspaces`)
- `GET /v1/workspaces` - List workspaces
- `POST /v1/workspaces` - Create workspace
- `PUT /v1/workspaces/:id` - Update workspace
- `DELETE /v1/workspaces/:id` - Delete workspace

#### Approvals API (`/v1/approvals`)
- `GET /v1/approvals` - List approvals
- `POST /v1/approvals` - Create approval
- `PUT /v1/approvals/:id` - Update approval
- `DELETE /v1/approvals/:id` - Delete approval
- `GET /v1/approvals/audit` - Get audit log

#### Users & Roles (`/v1/users`, `/v1/roles`)
- `GET /v1/users` - List users (with pagination)
- `PUT /v1/users/:id` - Update user
- `POST /v1/users/:id/reset-profile` - Reset profile
- `POST /v1/users/:id/reset-settings` - Reset settings
- `GET /v1/roles` - List roles
- `GET /v1/me` - Get current user
- `PUT /v1/me` - Update current user

#### Data Catalog (`/v1/data-objects`, `/v1/data-objects-catalog`, `/v1/data-object-versions`, `/v1/attributes-catalog`)
- `GET /v1/data-objects` - List lifecycle-managed data objects
- `GET /v1/rule-attributes` - Get rule attributes
- `POST /v1/rule-attributes` - Update rule attributes

Legacy note:
- Earlier migration drafts referenced `/v1/attributes` and `/v1/debug/raw-attributes`.
- The supported catalog attribute surface is `/v1/attributes-catalog`, aligned with `data_object_versions` and `attributes_catalog`.

#### Expanded Data Catalog (`/v1/data-products`, `/v1/data-sets`, etc.)
- `GET /v1/data-products` - List data products
- `GET /v1/data-sets` - List data sets
- `GET /v1/data-objects-catalog` - List cataloged data objects
- `GET /v1/data-object-versions` - List object versions
- `GET /v1/attributes-catalog` - List cataloged attributes
- `GET /v1/data-deliveries` - List data deliveries
- `GET /v1/attribute-rule-counts` - Get rule counts
- `POST /v1/data-object-versions/:versionId/generate-test-data` - Generate test data

#### Testing (`/v1/batch-test-requests`)
- `POST /v1/batch-test-requests` - Create batch test
- `GET /v1/batch-test-requests` - List batch tests
- `GET /v1/batch-test-requests/:id` - Get batch test
- `POST /v1/batch-test-requests/:id/run` - Run batch test

#### Authentication (`/v1/login`, `/v1/auth/*`)
- `POST /v1/login` - Login with credentials
- `POST /v1/logout` - Logout
- `GET /v1/auth/redirect` - OAuth2 redirect
- `GET /v1/auth/callback` - OAuth2 callback

#### Configuration (`/v1/app-config`)
- `GET /v1/app-config` - Get configuration
- `PUT /v1/app-config` - Update configuration

#### System (`/v1/system-info`)
- `GET /v1/system-info` - Get system information

#### Suggestions (`/v1/suggestions/*`)
- `GET /v1/suggestions/data-sources` - List data sources
- `POST /v1/suggestions/data-sources/:id/request-profiling` - Request profiling
- `GET /v1/suggestions` - List suggestions
- `POST /v1/suggestions/:id/accept` - Accept suggestion
- `POST /v1/suggestions/:id/dismiss` - Dismiss suggestion
- `POST /v1/suggestions/:id/apply` - Apply suggestion
- `GET /v1/suggestions/profiling-requests/:id/status` - Get profiling status
- `GET /v1/suggestions/metrics` - Get metrics
- `POST /v1/suggestions/metrics/clear` - Clear metrics

#### Data Contracts (`/v1/data-contracts/*`)
- `GET /v1/data-contracts` - List ODCS contracts
- `GET /v1/data-contracts/:id` - Get contract (YAML/JSON)
- `GET /v1/data-contracts/:id/quality-rules` - Extract quality rules

#### Health & Metadata (`/v1/health`, `/v1/ready`, `/v1/live`, `/v1/info`)
- `GET /v1/health` - Health check (database, redis)
- `GET /v1/ready` - Readiness probe
- `GET /v1/live` - Liveness probe
- `GET /v1/info` - API metadata

## Breaking Changes

### For API Consumers

**All existing API calls will break immediately.** Consumers must update all API URLs to include `/v1/` prefix.

#### Frontend (dq-ui) Changes Required

Update all API client calls in `dq-ui/src/`:

```typescript
// OLD
const response = await fetch('/api/rules')
const response = await fetch('/api/suggestions/data-sources')

// NEW
const response = await fetch('/v1/rules')
const response = await fetch('/v1/suggestions/data-sources')
```

**Migration Script** (recommended):
```bash
# In dq-ui/src directory
find . -type f \( -name "*.ts" -o -name "*.tsx" \) -exec sed -i '' \
  -e "s|'/rules|'/v1/rules|g" \
  -e "s|'/workspaces|'/v1/workspaces|g" \
  -e "s|'/approvals|'/v1/approvals|g" \
  -e "s|'/users|'/v1/users|g" \
  -e "s|'/api/suggestions|'/v1/suggestions|g" \
  -e "s|'/api/data-contracts|'/v1/data-contracts|g" \
  {} +
```

### For External Integrations

Any external systems calling the API must update URLs immediately. No backward compatibility period.

**Communication Template:**
```
Subject: BREAKING CHANGE - API Versioning Implemented

The DQ API has migrated to versioned endpoints. All endpoints now require /v1/ prefix.

Effective: [Deployment Date]
Action Required: Update all API URLs to include /v1/

Examples:
- /rules → /v1/rules
- /api/suggestions → /v1/suggestions
- /api/data-contracts → /v1/data-contracts

Documentation: [API_DOCS_URL]/api-docs
Support: [YOUR_CONTACT]
```

## OpenAPI Documentation

All endpoints now have complete OpenAPI decorators:
- `@ApiTags` - Grouped by resource
- `@ApiOperation` - Summary and description
- `@ApiParam` - Path parameters
- `@ApiQuery` - Query parameters
- `@ApiResponse` - Status codes and descriptions

**Access Documentation:**
- Interactive UI: `http://localhost:4001/api-docs`
- JSON Spec: `http://localhost:4001/api-docs/json`

## Validation

### Build Status
✅ TypeScript compilation successful
✅ No linting errors

### Deployment Checklist

- [ ] Backend deployed with new routes
- [ ] Frontend updated with new API URLs
- [ ] Integration tests updated
- [ ] External consumers notified
- [ ] API documentation updated
- [ ] Gateway configuration updated (if applicable)
- [ ] Monitoring dashboards updated to track `/v1/*` endpoints

## Rollback Plan

If critical issues arise:

1. **Revert backend deployment** to previous version
2. **Frontend will continue working** with old deployed backend
3 **Time window**: ~15 minutes for backend rollback

**No data migration required** - this is purely routing changes.

## Future Considerations

### When to Introduce v2

Introduce `/v2/*` when:
- Breaking changes to request/response format
- Major authentication model change
- Significant architectural refactoring

### Deprecation Process for v1

When v2 is ready:
1. Announce v1 deprecation with 6-month notice
2. Add deprecation warnings to v1 responses (`Deprecated: true` header)
3. Monitor v1 usage metrics
4. Provide migration tooling/docs
5. Remove v1 endpoints after deprecation period

## References

- [API_GATEWAY_DESIGN.md](./API_GATEWAY_DESIGN.md) - Gateway architecture
- [ARCHITECTURAL_DECISIONS.md](../architecture/ARCHITECTURAL_DECISIONS.md) - ADR-006: Versioned API Routes
- [ODCS_INTEGRATION.md](./ODCS_INTEGRATION.md) - Data contract endpoints

## Rationale: Why Big Bang?

**Advantages:**
✅ Clean break - no ambiguity  
✅ Simpler codebase - no dual-path logic  
✅ Forces immediate adoption  
✅ Clear migration moment  
✅ Easier testing (no mixed-version scenarios)

**Disadvantages:**
⚠️ Requires coordinated deployment  
⚠️ Higher immediate impact on consumers  
⚠️ No gradual rollout safety net

**Decision Factors:**
- Small number of consumers (primarily dq-ui)
- Controlled deployment environment
- Fast iteration cycle
- Team can coordinate UI + API deployment

## Success Metrics

Track these post-deployment:

1. **Adoption**: 100% of requests to `/v1/*` within 24 hours
2. **Error Rate**: < 1% 4xx/5xx errors on new endpoints
3. **Performance**: Response times unchanged from `/` to `/v1/`
4. **Documentation**: OpenAPI spec accessible at `/api-docs`

## Support

For issues or questions:
- Check `/v1/health` for backend status
- Review OpenAPI docs at `/api-docs`
- Check logs for correlation IDs (RFC 7807 errors include `traceId`)
