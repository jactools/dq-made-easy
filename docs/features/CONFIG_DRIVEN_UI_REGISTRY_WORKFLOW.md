# Config-Driven UI Registry Workflow

This workflow describes how the UI registry is supplied and maintained without committing protected registry contents to git.

## Delivery

The API exposes the active registry snapshot from `/api/system/v1/ui-registry`. When a registry entry references custom stylesheet assets, those assets are imported once through `POST /api/system/v1/ui-registry/assets/import` and then served back only from local API URLs under `/api/system/v1/ui-registry/assets/{kind}/{file_name}`.

Registry sources can come from the API-managed manifest, an environment payload, a file path, or a deployment-provided URL. If the registry cannot be loaded or validated, the app falls back to the built-in defaults and preserves app-owned primitives.

## Adding Entries

1. Update the external registry manifest with the new style or component bundle entry.
2. For remote stylesheet assets, import the asset through the API so the runtime only references a local URL.
3. Confirm the entry has a resolver, adapter, or fallback path before shipping it.

## Fallback Behavior

- Unknown style and component entries survive normalization and persistence.
- Inactive or unmapped component bundles fall back to builtin provider labels and selections.
- Remote stylesheet URLs are ignored at runtime unless they were first imported and re-served locally.

## UI and API Flow

The application settings page shows the current registry snapshot, the active style package options, and the resolved component bundles. The imported asset endpoints are the only supported way to host custom stylesheet assets at runtime.
