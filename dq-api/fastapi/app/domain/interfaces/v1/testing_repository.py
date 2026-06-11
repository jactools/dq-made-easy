from typing import Protocol

from typing import Any

from app.domain.entities.testing import (
    BatchTestRequestEntity,
    BatchTestRunResultEntity,
    StoreTestProofResultEntity,
    TestDataPayloadEntity,
    TestProofEntity,
    TestRunResultEntity,
)


class TestingRepository(Protocol):
    def generate_test_data_for_version(self, version_id: str, sample_count: int = 10) -> TestDataPayloadEntity: ...

    def run_rule_with_generated_data(
        self,
        rule_id: str,
        version_id: str,
        sample_count: int = 10,
        compiled_expression: str | None = None,
        semantic_config: dict[str, Any] | None = None,
    ) -> TestRunResultEntity: ...

    def create_test_proof(self, rule_id: str, test_data: dict, status: str = "pending") -> TestProofEntity: ...

    def update_test_proof(self, proof_id: str, test_data: dict, status: str | None = None) -> TestProofEntity: ...

    def store_test_proof(self, rule_id: str, test_data: dict) -> StoreTestProofResultEntity: ...

    def run_rule_against_test_data(
        self,
        rule_id: str,
        test_data: list[dict],
        version_id_source: str | None = None,
        compiled_expression: str | None = None,
        semantic_config: dict[str, Any] | None = None,
    ) -> TestRunResultEntity: ...

    def create_batch_test_requests(
        self,
        rule_ids: list[str],
        test_data_config: dict | None = None,
        requested_by: str | None = None,
        workspace: str | None = None,
    ) -> list[BatchTestRequestEntity]: ...

    def list_batch_test_requests(self, workspace: str | None = None, status: str | None = None) -> list[BatchTestRequestEntity]: ...

    def get_batch_test_request(self, request_id: str) -> BatchTestRequestEntity | None: ...

    def run_batch_test_request(self, request_id: str) -> BatchTestRunResultEntity: ...

    def list_test_proofs(self, rule_id: str) -> list[TestProofEntity]: ...
