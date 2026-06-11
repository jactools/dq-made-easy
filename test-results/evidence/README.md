# Test Evidence

Store generated run evidence here, organized by app version first.

Preferred layout:

- `test-results/evidence/<app_version>/api/<timestamp>-<label>/`
- `test-results/evidence/<app_version>/ui/<timestamp>-<label>/`
- `test-results/evidence/<app_version>/command/<timestamp>-<label>/`
- `test-results/evidence/<app_version>/test-proof/<proof_type>/<script_stem>/`

Use this folder for raw command output, logs, status files, and other transient evidence. Curated proof summaries belong in `test-results/test-proof/`.

## How To Create Evidence

1. Run tests through `scripts/run_test_evidence.sh ui`, `scripts/run_test_evidence.sh api`, or `scripts/run_test_evidence.sh command` so the helper writes evidence into the versioned folder for the current app release.
1. Keep the command output, metadata, status, logs, and any generated JUnit XML or screenshots in this folder.
1. Promote only the reviewed summary into `test-results/test-proof/<app_version>/<proof_type>/`.
1. Use `scripts/validate_test_proof.sh` after creating proof JSON so the committed summary stays schema-valid.