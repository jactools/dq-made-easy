# Security Features

- [ ] #SEC-1 Internal service-to-service TLS
- [ ] #SEC-2 Post-quantum cryptography readiness
- [ ] #SEC-3 Synthetic/test bucket and evidence boundaries
- [ ] #SEC-4 Controlled container egress and approved external destinations
- [ ] #SEC-5 Sensitive data encryption-at-rest and key segregation

## Split Security Planning Documents

- [SEC-1 Internal Service-to-Service TLS](./SEC_1_INTERNAL_SERVICE_TLS.md)
- [SEC-2 Post-Quantum Cryptography Readiness](./SEC_2_POST_QUANTUM_READINESS.md)
- [SEC-3 Synthetic/Test Bucket and Evidence Boundaries](./SEC_3_SYNTHETIC_TEST_BUCKET_AND_EVIDENCE_BOUNDARIES.md)
- [SEC-4 Controlled Container Egress and Approved External Destinations](./SEC_4_CONTROLLED_CONTAINER_EGRESS_AND_APPROVED_EXTERNAL_DESTINATIONS.md)
- [SEC-5 Sensitive Data Encryption-at-Rest and Key Segregation](./SEC_5_SENSITIVE_DATA_ENCRYPTION_AND_KEY_SEGREGATION.md)

## Notes

- Security tracks cover cross-stack protection work that spans API, workers, gateway, metadata, observability, and stateful infrastructure.
- SEC-1 is intentionally separate from [API-4 Advanced Authentication Options](./API_4_AUTHENTICATION_OPTIONS.md) because transport protection is broader than user and token authentication flows.
- SEC-2 focuses on cryptographic readiness and migration planning across repository-managed and vendor-managed security surfaces rather than immediate production-wide algorithm replacement.
- SEC-3 focuses on separating synthetic/test object-storage results from real/evidence object-storage results so test outputs are not misrepresented as production or reporting evidence.
- SEC-4 focuses on deny-by-default public internet egress from containers, with approved external destinations restricted to `jaccloud.nl` and `jacloud.nl` through a real enforcement layer rather than Compose-only controls.
- SEC-5 focuses on encryption-at-rest coverage and key-management blast-radius control for sensitive data, with an explicit prohibition on one shared encryption key for all sensitive attributes.