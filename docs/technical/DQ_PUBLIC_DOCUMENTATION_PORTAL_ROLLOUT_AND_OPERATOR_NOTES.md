# Public Documentation Portal Rollout and Operator Notes

This note records the current public documentation surface at `/docs`.

**Current release line**: `v0.11.0`

## Audience

- Operators running the dq-rulebuilder stack
- Maintainers responsible for the public documentation site

## What Is Enabled

- A static Docusaurus 3 site is built for the public docs portal
- The site uses Infima-based styling and serves from `/docs/`
- The build output is copied into `dq-ui/public/docs/` and served by the frontend container's nginx configuration
- Repository docs from `docs/` and architecture docs from `architecture/` are consumed directly by the Docusaurus site as separate content roots
- The public build no longer mirrors source docs into a site-local authoring tree
- Public docs are readable without login and remain separate from authenticated application routes

## Current Site Structure

The portal includes dedicated sections for:

- Public access guidance
- Feature plans and implementation details
- Technical references and rollout notes
- Current status and roadmap docs
- Release notes and engineering decisions
- Architecture and ADR content
- User manuals
- API reference links

The site uses default Docusaurus styling with light and dark color-mode support.

## Rollout Guidance

1. Deploy the UI build that includes the copied public docs output before advertising the documentation URL externally.
2. Confirm unauthenticated users can load `/docs` directly and browse the content without a login prompt.
3. Keep the public documentation experience separate from workspace-scoped application pages and auth-only navigation.
4. Update authored docs in `docs/` or `architecture/`; do not hand-edit any legacy site-local copies.
5. Keep changes focused so the public route stays available throughout future updates.

## Validation Expectations

Run the focused docs build pipeline from `dq-ui`:

```bash
bash scripts/build-public-docs.sh
```

Expected outcomes:

- the Docusaurus site builds successfully
- the generated files are copied into `dq-ui/public/docs/`
- nginx serves the static docs portal from `/docs/`

## Troubleshooting

- If `/docs` still shows a login prompt, confirm the frontend image contains the copied static docs tree and the nginx route is present.
- If the public docs path 404s, confirm the built site was copied into `dq-ui/public/docs/` and the frontend build picked it up.
- If the Docusaurus build fails, confirm the docs-site dependencies are installed and the root `docs/` and `architecture/` trees are still well-formed for Docusaurus.

## References

- [dq-ui docs site](../../dq-ui/docs-site)
- [dq-ui build-public-docs script](../../dq-ui/scripts/build-public-docs.sh)
- [dq-ui nginx config](../../dq-ui/nginx/default.conf)