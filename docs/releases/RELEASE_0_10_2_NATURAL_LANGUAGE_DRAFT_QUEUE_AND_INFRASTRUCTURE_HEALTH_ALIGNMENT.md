# Release v0.10.2 — Natural-Language Draft Queue and Infrastructure Health Alignment

**Release date**: 2026-05-09
**UI version**: `0.10.2`
**API version**: `0.10.2`

## Summary

This patch release tightens the natural-language drafting workflow, queues LLM-backed requests behind Redis, and hardens the dq-llm and infrastructure health surfaces so operators can see the full request and service lifecycle end to end.

## Included in this release

- UI package metadata is aligned to `0.10.2`
- API package metadata is aligned to `0.10.2`
- Version markers in `VERSION_MANIFEST.json` are aligned for the changed tracked components: `Infrastructure` and `Documentation`
- The Suggestions flow now uses a single Accept action that creates the rule directly, and the separate Apply-as-Rule path was removed
- Natural-language rule drafting now supports RapidFuzz vs LLM provider selection, queues LLM requests behind Redis, and tracks request progress in the UI
- dq-llm startup health now passes with the callable registry wrapper, and the OpenMetadata configure/sync helpers now include the shared logging support they require at runtime
- Grafana infrastructure health now includes dq-llm container status, and the queue/backlog dashboards surface natural-language draft activity

## User-visible impact

- Users now confirm a suggestion with one action: Accept creates the rule and finishes the flow
- Rule draft generation can be evaluated with RapidFuzz first or handed off to the queued LLM path when desired
- Draft requests now show queue-aware progress instead of appearing to hang while dq-llm works
- Operators can see dq-llm container health directly in the infrastructure dashboard, alongside the queue metrics that drive the drafting flow

## Key implementation files

- [VERSION_MANIFEST.json](../../VERSION_MANIFEST.json)
- [dq-ui/package.json](../../dq-ui/package.json)
- [dq-api/package.json](../../dq-api/package.json)
- [dq-ui/package-lock.json](../../dq-ui/package-lock.json)
- [dq-api/package-lock.json](../../dq-api/package-lock.json)
- [dq-ui/src/components/Suggestions.tsx](../../dq-ui/src/components/Suggestions.tsx)
- [dq-ui/src/components/NaturalLanguageRuleDraft.tsx](../../dq-ui/src/components/NaturalLanguageRuleDraft.tsx)
- [dq-ui/src/contexts/AsyncRequestTrackerContext.tsx](../../dq-ui/src/contexts/AsyncRequestTrackerContext.tsx)
- [dq-ui/src/hooks/useSuggestions.ts](../../dq-ui/src/hooks/useSuggestions.ts)
- [dq-api/fastapi/app/api/v1/endpoints/suggestions.py](../../dq-api/fastapi/app/api/v1/endpoints/suggestions.py)
- [dq-api/fastapi/app/application/services/natural_language_rule_drafting.py](../../dq-api/fastapi/app/application/services/natural_language_rule_drafting.py)
- [dq-api/fastapi/app/application/services/natural_language_draft_enqueue_service.py](../../dq-api/fastapi/app/application/services/natural_language_draft_enqueue_service.py)
- [dq-api/fastapi/app/application/services/natural_language_draft_queue_worker.py](../../dq-api/fastapi/app/application/services/natural_language_draft_queue_worker.py)
- [dq-api/fastapi/app/core/otel_metrics.py](../../dq-api/fastapi/app/core/otel_metrics.py)
- [dq-llm/entrypoint.py](../../dq-llm/entrypoint.py)
- [dq-llm/warm_cache.py](../../dq-llm/warm_cache.py)
- [dq-metadata/Dockerfile.configure](../../dq-metadata/Dockerfile.configure)
- [dq-metadata/scripts/configure_openmetadata_container.sh](../../dq-metadata/scripts/configure_openmetadata_container.sh)
- [observability/container-metrics/container_metrics_exporter.py](../../observability/container-metrics/container_metrics_exporter.py)
- [observability/grafana/provisioning/dashboards/dq-api-observability.json](../../observability/grafana/provisioning/dashboards/dq-api-observability.json)
- [observability/grafana/provisioning/dashboards/dq-infrastructure-health.json](../../observability/grafana/provisioning/dashboards/dq-infrastructure-health.json)

## Documentation updated

- [RELEASE_NOTES_USER.md](../../RELEASE_NOTES_USER.md)
- [dq-ui/public/release-notes/RELEASE_NOTES_USER.md](../../dq-ui/public/release-notes/RELEASE_NOTES_USER.md)
- [README.md](../../README.md)
- [docs/releases/README.md](./README.md)
- [docs/technical/DEPLOYMENT.md](../technical/DEPLOYMENT.md)
- [docs/technical/QUICKSTART_DEPLOY.md](../technical/QUICKSTART_DEPLOY.md)
- [docs/technical/AUTOMATIC_VERSIONING.md](../technical/AUTOMATIC_VERSIONING.md)
- [TECHNICAL.md](../../TECHNICAL.md)

## Notes

- Repo-managed Docker image tags stay on the `0.10-<hash>` release line because image tags derive from the `major.minor` base in `VERSION_MANIFEST.json`.
- The release note copy under `dq-ui/public/release-notes/` should stay in sync with the root `RELEASE_NOTES_USER.md`.