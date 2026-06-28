# ADR-010: ApiService Decomposition into Focused Sub-Services

**Status**: ✅ Implemented  
**Date**: 2026-03-11

### Context
`server/api.service.ts` grew to over 3,050 lines, combining application configuration, data catalog queries, rule testing/batch execution, JWT helpers, and rule expression evaluation in a single class. This made the file hard to navigate, review, and test in isolation.

### Decision
Split `ApiService` into purpose-scoped modules while keeping `ApiService` as the single facade that `AppController` and `AuthMiddleware` depend on (no changes to callers).

**New layout**:

```
server/
├── api.service.ts          # Thin facade (~550 lines) — workspace, rules,
│                           # approvals, users, auth/OIDC, system info
├── services/
│   ├── app-config.service.ts    # getAppConfig() + setAppConfig()
│   ├── data-catalog.service.ts  # 7 data catalog query methods
│   └── testing.service.ts       # batch testing, test proofs, concurrency limit
└── utils/
    ├── rule-evaluation.utils.ts # pure join/expression evaluation helpers
    └── jwt.utils.ts             # JWT decode / validation helpers
```

**Injection chain**:
```
AppModule providers:
  AppConfigService  (no deps)
  DataCatalogService (no deps)
  TestingService    → AppConfigService
  ApiService        → AppConfigService, DataCatalogService, TestingService
```

`ApiService` delegates via thin one-liner methods (e.g. `getAppConfig() { return this.appConfigSvc.getAppConfig(); }`). No caller changes were needed.

Shared mutable state (`currentUserId`, `sessions`, `pendingOidcStates`) stays on `ApiService` because `AuthMiddleware` directly reads/writes those fields.

### Consequences
**Positive**:
- Each file has a single, clear responsibility
- `AppConfigService` and `DataCatalogService` are independently unit-testable without standing up the full service
- Pure utility functions in `utils/` are importable by both `ApiService` and `TestingService` without circular dependencies
- Build remains clean (zero TypeScript errors)

**Negative**:
- Slightly more files to navigate (mitigated by clear naming)
- Constructor injection means all three sub-services are instantiated even in test harnesses that only need one (acceptable tradeoff)

---

