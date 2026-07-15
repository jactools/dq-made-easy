# Config-Driven UI Registry Workflow

This workflow describes how the UI registry is supplied and maintained without committing protected registry contents to git.

## Delivery

The API exposes the active registry snapshot from `/api/system/v1/ui-registry`. When a registry entry references custom stylesheet assets, those assets are imported once through `POST /api/system/v1/ui-registry/assets/import` and then served back only from local API URLs under `/api/system/v1/ui-registry/assets/&#123;kind&#125;/&#123;file_name&#125;`.

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

Bundle upload rule: style bundles may include a `package.json` plus supporting assets such as fonts or favicons. The importer uses the package metadata and archive layout to locate the stylesheet entry and keep sibling assets local. Component bundles must still contain a single loadable entry file such as `index.js` or `icons.mjs`, not a full `dist/` directory.

## Admin Workflow In The App

If you have downloaded custom UI styles or component bundles, use the app as an admin in this order:

1. Import any custom stylesheet assets through the API so they are stored under the local registry asset endpoints.
2. Update the external registry manifest with the new style or component bundle entry, including the asset reference and adapter or fallback path.
3. Open the application settings page and confirm the registry snapshot now shows the new style package or component bundle option.
4. Select the desired registry entry in settings and save the configuration so the app records only the registry identifier and minimal runtime metadata.
5. Refresh the UI and verify the new styles or component bundle are active.
6. If the registry fails to load or an entry is inactive, the app falls back to the built-in defaults while preserving the saved registry value.

## Validity Criteria For A Usable Bundle

A custom UI style or component bundle is considered usable only when all of these are true:

1. The entry appears in the **UI Registry** snapshot on **Admin** → **App Settings**.
2. The uploaded style archive exposed a discoverable stylesheet entry, and the extracted style asset is served from a local API URL, not a raw remote stylesheet URL.
3. The component bundle has a resolver, adapter, or fallback path in the registry, and the archive contained one loadable entry file rather than a whole `dist/` tree.
4. The entry is not marked inactive or unmapped in the registry snapshot.
5. The selected value is saved as a registry identifier, and the app still shows the entry after refresh.

If any of those checks fail, treat the bundle as not ready for admin activation and correct the registry first.
