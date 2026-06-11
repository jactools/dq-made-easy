from uuid import uuid4
from datetime import datetime
import json

from app.application.services import evaluate_expression_on_context_with_details
from app.domain.entities.testing import (
    BatchTestRequestEntity,
    BatchTestRunResultEntity,
    StoreTestProofResultEntity,
    TestDataPayloadEntity,
    TestProofEntity,
    TestRowResultEntity,
    TestRunResultEntity,
)
from app.domain.interfaces.v1.testing_repository import TestingRepository
from app.infrastructure.repositories.in_memory_test_data import testing_seed_data


class InMemoryTestingRepository(TestingRepository):
    def __init__(self) -> None:
        self._test_proofs, self._version_catalog, self._rules = testing_seed_data()
        self._batch_test_requests: list[BatchTestRequestEntity] = [
            BatchTestRequestEntity(
                id="batch-seed-001",
                ruleId="rule-email-format",
                requestedBy="system",
                requestedAt="2026-03-01T00:00:00Z",
                testDataConfig={"seeded": True},
                executionCorrelationId=None,
                status="pending",
                workspace="default",
                completedAt=None,
                proofId=None,
            )
        ]

    def generate_test_data_for_version(self, version_id: str, sample_count: int = 10) -> TestDataPayloadEntity:
        version = self._version_catalog.get(version_id)
        if not version:
            return TestDataPayloadEntity(
                versionId=version_id,
                versionName=None,
                dataObjectId=None,
                attributeCount=0,
                sampleCount=sample_count,
                samples=[],
                attributes=[],
                generatedAt="2026-03-01T00:00:00Z",
            )

        attributes = list(version["attributes"])
        samples = [
            {
                "email": f"user{i + 1}@example.com",
                "status": "active" if i % 2 == 0 else "inactive",
            }
            for i in range(sample_count)
        ]
        return TestDataPayloadEntity(
            versionId=version_id,
            versionName=version["version"],
            dataObjectId=version["data_object_id"],
            attributeCount=len(attributes),
            sampleCount=sample_count,
            samples=samples,
            attributes=attributes,
            generatedAt="2026-03-01T00:00:00Z",
        )

    def run_rule_with_generated_data(
        self,
        rule_id: str,
        version_id: str,
        sample_count: int = 10,
        compiled_expression: str | None = None,
        semantic_config: dict | None = None,
    ) -> TestRunResultEntity:
        generated = self.generate_test_data_for_version(version_id, sample_count)
        return self.run_rule_against_test_data(
            rule_id,
            generated.samples,
            version_id,
            compiled_expression=compiled_expression,
            semantic_config=semantic_config,
        )

    @staticmethod
    def _normalize_test_proof_status(status: object, passed: object = None) -> str:
        normalized = str(status or "").strip().lower()
        if normalized in {"pending", "running", "passed", "failed"}:
            return normalized
        if passed is True:
            return "passed"
        if passed is False:
            return "failed"
        return "pending"

    @classmethod
    def _build_execution_trace(
        cls,
        *,
        test_date: str,
        proof_data: dict,
        test_data: dict,
        status: str,
        existing_execution_trace: dict | None = None,
    ) -> dict:
        execution_trace = dict(existing_execution_trace or {})
        execution_trace.update(dict(test_data.get("executionTrace") or {}))
        execution_trace.setdefault("executionId", f"exec-{uuid4().hex[:12]}")
        execution_trace.setdefault("correlationId", f"corr-{uuid4().hex[:12]}")
        if status in {"passed", "failed"}:
            execution_trace["executedAt"] = str(execution_trace.get("executedAt") or test_date)
        else:
            execution_trace.setdefault("executedAt", None)
        execution_trace["resultStatus"] = status
        proof_data["executionTrace"] = execution_trace
        proof_data["requestStatus"] = status
        return execution_trace

    def store_test_proof(self, rule_id: str, test_data: dict) -> StoreTestProofResultEntity:
        records_tested = int(test_data.get("recordsTestedCount") or 0)
        failures_found = int(test_data.get("failuresFound") or 0)
        success_rate = ((records_tested - failures_found) / records_tested * 100) if records_tested > 0 else 0
        proof_data = dict(test_data.get("proofData") or {})
        metrics = dict(test_data.get("metrics") or {}) or None
        diagnostics = list(test_data.get("diagnostics") or []) or None
        test_date = "2026-03-01T00:00:00Z"
        status = self._normalize_test_proof_status(test_data.get("status"), test_data.get("passed"))
        execution_trace = self._build_execution_trace(
            test_date=test_date,
            proof_data=proof_data,
            test_data=test_data,
            status=status,
        )

        payload = {
            "proofId": f"proof-{len(self._test_proofs) + 1:03d}",
            "ruleId": rule_id,
            "testDate": test_date,
            "coverage": float(test_data.get("coverage") or 0),
            "passed": status == "passed",
            "recordsTestedCount": records_tested,
            "failuresFound": failures_found,
            "successRate": success_rate,
            "proofData": proof_data,
            "executionTrace": execution_trace,
            "metrics": metrics,
            "diagnostics": diagnostics,
        }
        self._test_proofs.append(
            {
                "id": payload["proofId"],
                "ruleId": rule_id,
                "testDate": payload["testDate"],
                "coverage": payload["coverage"],
                "status": status,
                "recordsTestedCount": records_tested,
                "failuresFound": failures_found,
                "testData": proof_data,
                "executionTrace": execution_trace,
                "metrics": metrics,
                "diagnostics": diagnostics,
            }
        )
        return StoreTestProofResultEntity(**payload)

    def create_test_proof(self, rule_id: str, test_data: dict, status: str = "pending") -> TestProofEntity:
        normalized_status = self._normalize_test_proof_status(status, test_data.get("passed"))
        proof_data = dict(test_data.get("proofData") or {})
        test_date = str(test_data.get("testDate") or "2026-03-01T00:00:00Z")
        execution_trace = self._build_execution_trace(
            test_date=test_date,
            proof_data=proof_data,
            test_data=test_data,
            status=normalized_status,
        )
        row = {
            "id": f"proof-{len(self._test_proofs) + 1:03d}",
            "ruleId": rule_id,
            "testDate": test_date,
            "coverage": float(test_data.get("coverage") or 0),
            "status": normalized_status,
            "recordsTestedCount": int(test_data.get("recordsTestedCount") or 0),
            "failuresFound": int(test_data.get("failuresFound") or 0),
            "testData": proof_data,
            "executionTrace": execution_trace,
            "metrics": dict(test_data.get("metrics") or {}) or None,
            "diagnostics": list(test_data.get("diagnostics") or []) or None,
        }
        self._test_proofs.append(row)
        return TestProofEntity(
            id=row["id"],
            ruleId=rule_id,
            testDate=row["testDate"],
            coverage=row["coverage"],
            status=row["status"],
            recordsTestedCount=row["recordsTestedCount"],
            failuresFound=row["failuresFound"],
            proofData=proof_data,
            executionTrace=execution_trace,
            metrics=row["metrics"],
            diagnostics=row["diagnostics"],
        )

    def update_test_proof(self, proof_id: str, test_data: dict, status: str | None = None) -> TestProofEntity:
        for row in self._test_proofs:
            if str(row.get("id")) != str(proof_id):
                continue

            normalized_status = self._normalize_test_proof_status(status or row.get("status"), test_data.get("passed"))
            existing_proof_data = dict(row.get("testData") or {})
            proof_data = {
                **existing_proof_data,
                **dict(test_data.get("proofData") or {}),
            }
            execution_trace = self._build_execution_trace(
                test_date=str(row.get("testDate") or "2026-03-01T00:00:00Z"),
                proof_data=proof_data,
                test_data=test_data,
                status=normalized_status,
                existing_execution_trace=dict(existing_proof_data.get("executionTrace") or {}),
            )
            row["coverage"] = float(test_data.get("coverage") if test_data.get("coverage") is not None else row.get("coverage") or 0)
            row["status"] = normalized_status
            row["recordsTestedCount"] = int(test_data.get("recordsTestedCount") if test_data.get("recordsTestedCount") is not None else row.get("recordsTestedCount") or 0)
            row["failuresFound"] = int(test_data.get("failuresFound") if test_data.get("failuresFound") is not None else row.get("failuresFound") or 0)
            row["testData"] = proof_data
            row["executionTrace"] = execution_trace
            if test_data.get("metrics") is not None:
                row["metrics"] = dict(test_data.get("metrics") or {}) or None
            if test_data.get("diagnostics") is not None:
                row["diagnostics"] = list(test_data.get("diagnostics") or []) or None
            return TestProofEntity(
                id=str(row.get("id") or ""),
                ruleId=str(row.get("ruleId") or ""),
                testDate=str(row.get("testDate") or ""),
                coverage=float(row.get("coverage") or 0),
                status=str(row.get("status") or "pending"),
                recordsTestedCount=int(row.get("recordsTestedCount") or 0),
                failuresFound=int(row.get("failuresFound") or 0),
                proofData=proof_data,
                executionTrace=execution_trace,
                metrics=dict(row.get("metrics") or {}) or None,
                diagnostics=list(row.get("diagnostics") or []) or None,
            )

        raise KeyError(f"test_proof {proof_id} not found")

    def run_rule_against_test_data(
        self,
        rule_id: str,
        test_data: list[dict],
        version_id_source: str | None = None,
        compiled_expression: str | None = None,
        semantic_config: dict | None = None,
    ) -> TestRunResultEntity:
        rule = self._rules.get(rule_id, {"name": "Unknown", "dimension": "unknown", "description": "", "expression": ""})
        expression_to_execute = str(compiled_expression or rule["expression"])
        dataset_pass_map = self._dataset_pass_map_for_expression(expression_to_execute, test_data)
        semantic_stats = self._create_semantic_stats(semantic_config)
        matcher = self._build_rule_matcher(
            expression_to_execute,
            semantic_config=semantic_config,
            semantic_stats=semantic_stats,
        )
        results: list[TestRowResultEntity] = []
        evaluation_warning: str | None = None
        for index, row in enumerate(test_data):
            try:
                passed = dataset_pass_map[index] if dataset_pass_map is not None else matcher(row)
            except ValueError as exc:
                evaluation_warning = str(exc)
                passed = False
            results.append(TestRowResultEntity(
                rowIndex=index,
                data=row,
                passed=passed,
                joinEvaluated=False,
                joinMatchedContexts=0,
            ))

        passed_count = len([entry for entry in results if entry.passed])
        failed_count = len(results) - passed_count
        total = len(results)
        success_rate = (passed_count / total * 100) if total else 0
        check_type = str(rule.get("check_type") or "").strip().upper() or None
        raw_params = rule.get("check_type_params")
        if isinstance(raw_params, str):
            try:
                check_type_params = json.loads(raw_params)
            except json.JSONDecodeError:
                check_type_params = {}
        else:
            check_type_params = dict(raw_params or {})
        rule_passed, required_success_rate = self._evaluate_rule_pass(
            check_type,
            check_type_params,
            success_rate,
            failed_count,
        )
        semantic_context = {
            "enabled": bool(semantic_stats.get("enabled")),
            "configured": bool(semantic_stats.get("configured")),
            "fieldAliasHits": int(semantic_stats.get("field_alias_hits", 0)),
            "valueCoercionMatches": int(semantic_stats.get("value_coercion_matches", 0)),
            "semanticCoercionUsed": bool(
                int(semantic_stats.get("field_alias_hits", 0)) > 0
                or int(semantic_stats.get("value_coercion_matches", 0)) > 0
            ),
        }

        return TestRunResultEntity(
            ruleId=rule_id,
            expression=expression_to_execute,
            testDataSource=version_id_source or "manual",
            totalTests=total,
            passedCount=passed_count,
            failedCount=failed_count,
            successRate=round(success_rate, 2),
            rulePassed=rule_passed,
            requiredSuccessRate=required_success_rate,
            timestamp="2026-03-01T00:00:00Z",
            results=results,
            ruleDetails={
                "name": rule["name"],
                "dimension": rule["dimension"],
                "description": rule["description"],
                **({"evaluationWarning": evaluation_warning} if evaluation_warning else {}),
            },
            executionContext=(
                {
                    **({"reason": "expression-not-executable", "message": evaluation_warning} if evaluation_warning else {}),
                    "semanticMatching": semantic_context,
                }
            ),
        )

    @staticmethod
    def _create_semantic_stats(semantic_config: dict | None) -> dict:
        config = dict(semantic_config or {})
        field_alias_mappings = config.get("fieldAliasMappings")
        alias_map = (
            {
                str(key).strip(): str(value).strip()
                for key, value in dict(field_alias_mappings or {}).items()
                if str(key).strip() and str(value).strip()
            }
            if isinstance(field_alias_mappings, dict)
            else {}
        )
        return {
            "enabled": bool(config.get("enabled")),
            "configured": bool(alias_map) or bool(config.get("enabled")),
            "field_alias_mappings": alias_map,
            "field_alias_hits": 0,
            "value_coercion_matches": 0,
        }

    @staticmethod
    def _canonical_semantic_token(value: object, semantic_config: dict | None) -> str | None:
        if isinstance(value, bool):
            return "active" if value else "inactive"

        normalized = str(value or "").strip().lower()
        if not normalized:
            return None

        config = dict(semantic_config or {})
        active_synonyms = config.get("activeSynonyms")
        inactive_synonyms = config.get("inactiveSynonyms")
        active_set = {
            str(item).strip().lower()
            for item in (active_synonyms if isinstance(active_synonyms, list) else ["active", "enabled", "true", "1", "yes", "on"])
            if str(item).strip()
        }
        inactive_set = {
            str(item).strip().lower()
            for item in (inactive_synonyms if isinstance(inactive_synonyms, list) else ["inactive", "disabled", "false", "0", "no", "off"])
            if str(item).strip()
        }

        if normalized in active_set:
            return "active"
        if normalized in inactive_set:
            return "inactive"
        return None

    @staticmethod
    def _build_rule_matcher(
        expression: str,
        semantic_config: dict | None = None,
        semantic_stats: dict | None = None,
    ):
        import re

        contains_match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+contains\s+'([^']*)'\s*", expression)
        if contains_match:
            field_name, expected = contains_match.groups()

            def contains_matcher(row: dict) -> bool:
                value = row.get(field_name)
                return isinstance(value, str) and expected in value

            return contains_matcher

        regex_match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*~\s*'([^']*)'\s*", expression)
        if regex_match:
            field_name, pattern = regex_match.groups()
            compiled = re.compile(pattern)

            def regex_matcher(row: dict) -> bool:
                value = row.get(field_name)
                return isinstance(value, str) and compiled.search(value) is not None

            return regex_matcher

        equality_match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'([^']*)'\s*", expression)
        if equality_match:
            field_name, expected = equality_match.groups()

            def equality_matcher(row: dict) -> bool:
                stats = semantic_stats or {}
                alias_map = dict(stats.get("field_alias_mappings") or {})
                resolved_field_name = field_name
                if resolved_field_name not in row and field_name in alias_map and alias_map[field_name] in row:
                    resolved_field_name = alias_map[field_name]
                    stats["field_alias_hits"] = int(stats.get("field_alias_hits", 0)) + 1

                value = row.get(resolved_field_name)
                if value == expected:
                    return True

                if not bool((semantic_config or {}).get("enabled")):
                    return False

                actual_token = InMemoryTestingRepository._canonical_semantic_token(value, semantic_config)
                expected_token = InMemoryTestingRepository._canonical_semantic_token(expected, semantic_config)
                if actual_token and expected_token and actual_token == expected_token:
                    stats["value_coercion_matches"] = int(stats.get("value_coercion_matches", 0)) + 1
                    return True
                return False

            return equality_matcher

        trim_not_empty_match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+NULL\s+AND\s+TRIM\(\1\)\s*!=\s*''\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if trim_not_empty_match:
            (field_name,) = trim_not_empty_match.groups()

            def trim_not_empty_matcher(row: dict) -> bool:
                value = row.get(field_name)
                if value is None:
                    return False
                return str(value).strip() != ""

            return trim_not_empty_matcher

        not_default_match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+NULL\s+AND\s+\1\s*!=\s*'([^']*)'\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if not_default_match:
            field_name, disallowed = not_default_match.groups()

            def not_default_matcher(row: dict) -> bool:
                value = row.get(field_name)
                if value is None:
                    return False
                return str(value) != disallowed

            return not_default_matcher

        lower_in_match = re.fullmatch(
            r"\s*LOWER\(([A-Za-z_][A-Za-z0-9_]*)\)\s+IN\s*\((.+)\)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if lower_in_match:
            field_name, values_blob = lower_in_match.groups()
            allowed_values = {v.lower() for v in re.findall(r"'([^']*)'", values_blob)}

            def lower_in_matcher(row: dict) -> bool:
                value = row.get(field_name)
                if value is None:
                    return False
                return str(value).lower() in allowed_values

            return lower_in_matcher

        lower_not_in_match = re.fullmatch(
            r"\s*LOWER\(([A-Za-z_][A-Za-z0-9_]*)\)\s+NOT\s+IN\s*\((.+)\)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if lower_not_in_match:
            field_name, values_blob = lower_not_in_match.groups()
            blocked_values = {v.lower() for v in re.findall(r"'([^']*)'", values_blob)}

            def lower_not_in_matcher(row: dict) -> bool:
                value = row.get(field_name)
                if value is None:
                    return True
                return str(value).lower() not in blocked_values

            return lower_not_in_matcher

        regex_matches_match = re.fullmatch(
            r"\s*REGEXP_MATCHES\(([A-Za-z_][A-Za-z0-9_]*),\s*'([^']*)'(?:,\s*'([a-zA-Z]*)')?\)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if regex_matches_match:
            field_name, pattern, flags = regex_matches_match.groups()
            regex_flags = 0
            if flags:
                if "i" in flags:
                    regex_flags |= re.IGNORECASE
                if "m" in flags:
                    regex_flags |= re.MULTILINE
                if "s" in flags:
                    regex_flags |= re.DOTALL
            compiled = re.compile(pattern, regex_flags)

            def regex_matches_matcher(row: dict) -> bool:
                value = row.get(field_name)
                if value is None:
                    return False
                return compiled.search(str(value)) is not None

            return regex_matches_matcher

        is_not_null_match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+NULL\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if is_not_null_match:
            (field_name,) = is_not_null_match.groups()

            def is_not_null_matcher(row: dict) -> bool:
                return row.get(field_name) is not None

            return is_not_null_matcher

        is_null_match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NULL\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if is_null_match:
            (field_name,) = is_null_match.groups()

            def is_null_matcher(row: dict) -> bool:
                return row.get(field_name) is None

            return is_null_matcher

        now_compare_match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*<=\s*NOW\(\)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if now_compare_match:
            (field_name,) = now_compare_match.groups()

            def now_compare_matcher(row: dict) -> bool:
                value = row.get(field_name)
                if value is None:
                    return False
                parsed = InMemoryTestingRepository._parse_datetime(value)
                return parsed is not None and parsed <= datetime.now(parsed.tzinfo)

            return now_compare_matcher

        datediff_now_match = re.fullmatch(
            r"\s*DATEDIFF\(NOW\(\),\s*([A-Za-z_][A-Za-z0-9_]*)\)\s*<=\s*(\d+)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if datediff_now_match:
            field_name, max_days_text = datediff_now_match.groups()
            max_days = int(max_days_text)

            def datediff_now_matcher(row: dict) -> bool:
                value = row.get(field_name)
                parsed = InMemoryTestingRepository._parse_datetime(value)
                if parsed is None:
                    return False
                age_days = (datetime.now(parsed.tzinfo) - parsed).total_seconds() / 86400
                return age_days <= max_days

            return datediff_now_matcher

        timestampdiff_hours_match = re.fullmatch(
            r"\s*TIMESTAMPDIFF\(HOUR,\s*([A-Za-z_][A-Za-z0-9_]*),\s*([A-Za-z_][A-Za-z0-9_]*)\)\s*<=\s*(\d+)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if timestampdiff_hours_match:
            start_field, end_field, max_hours_text = timestampdiff_hours_match.groups()
            max_hours = int(max_hours_text)

            def timestampdiff_hours_matcher(row: dict) -> bool:
                start = InMemoryTestingRepository._parse_datetime(row.get(start_field))
                end = InMemoryTestingRepository._parse_datetime(row.get(end_field))
                if start is None or end is None:
                    return False
                diff_hours = (end - start).total_seconds() / 3600
                return diff_hours <= max_hours

            return timestampdiff_hours_matcher

        def expression_matcher(row: dict) -> bool:
            passed, eval_error = evaluate_expression_on_context_with_details(expression, row)
            if eval_error:
                raise ValueError(
                    f"Expression is not executable by test evaluator: {eval_error}"
                )
            return passed

        return expression_matcher

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    @staticmethod
    def _dataset_pass_map_for_expression(expression: str, rows: list[dict]) -> list[bool] | None:
        import re

        uniqueness_match = re.fullmatch(
            r"\s*COUNT\(\*\)\s+OVER\s*\(\s*PARTITION\s+BY\s+(.+?)\s*\)\s*=\s*1\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if uniqueness_match:
            attrs_text = uniqueness_match.group(1)
            attributes = [a.strip() for a in attrs_text.split(",") if a.strip()]
            if not attributes:
                return [False for _ in rows]
            counts: dict[tuple[object, ...], int] = {}
            keys: list[tuple[object, ...]] = []
            for row in rows:
                key = tuple(row.get(attr) for attr in attributes)
                keys.append(key)
                counts[key] = counts.get(key, 0) + 1
            return [counts[key] == 1 for key in keys]

        ref_integrity_match = re.fullmatch(
            r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+IN\s*\(\s*SELECT\s+([A-Za-z_][A-Za-z0-9_]*)\s+FROM\s+([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*",
            expression,
            flags=re.IGNORECASE,
        )
        if ref_integrity_match:
            attribute, ref_attribute, _ref_object = ref_integrity_match.groups()
            reference_values = {row.get(ref_attribute) for row in rows if row.get(ref_attribute) is not None}
            return [row.get(attribute) in reference_values for row in rows]

        return None

    @staticmethod
    def _evaluate_rule_pass(
        check_type: str | None,
        check_type_params: dict,
        success_rate: float,
        failed_count: int,
    ) -> tuple[bool, float | None]:
        if str(check_type or "").upper() != "THRESHOLD":
            return failed_count == 0, None

        threshold_raw = check_type_params.get("threshold")
        if threshold_raw is None:
            return failed_count == 0, None

        try:
            required_success_rate = float(threshold_raw)
        except (TypeError, ValueError):
            return failed_count == 0, None

        required_success_rate = max(0.0, min(100.0, required_success_rate))
        operator = str(check_type_params.get("operator") or "gte").lower()

        if operator == "gt":
            return success_rate > required_success_rate, required_success_rate
        if operator == "lt":
            return success_rate < required_success_rate, required_success_rate
        if operator == "lte":
            return success_rate <= required_success_rate, required_success_rate
        return success_rate >= required_success_rate, required_success_rate

    def create_batch_test_requests(
        self,
        rule_ids: list[str],
        test_data_config: dict | None = None,
        requested_by: str | None = None,
        workspace: str | None = None,
    ) -> list[BatchTestRequestEntity]:
        config = test_data_config or {}
        actor = requested_by or "system"
        target_workspace = workspace or "default"
        start_index = len(self._batch_test_requests)
        created_rows = [
            BatchTestRequestEntity(
            id=f"batch-{start_index + index + 1}",
                ruleId=str(rule_id),
                requestedBy=actor,
                requestedAt="2026-03-01T00:00:00Z",
                testDataConfig=config,
                executionCorrelationId=None,
                status="pending",
                workspace=target_workspace,
                completedAt=None,
                proofId=None,
            )
            for index, rule_id in enumerate(rule_ids)
        ]
        self._batch_test_requests.extend(created_rows)
        return created_rows

    def list_batch_test_requests(
        self,
        workspace: str | None = None,
        status: str | None = None,
    ) -> list[BatchTestRequestEntity]:
        rows = self._batch_test_requests
        if workspace:
            rows = [row for row in rows if row.workspace == workspace]
        if status:
            rows = [row for row in rows if row.status == status]
        return list(rows)

    def get_batch_test_request(self, request_id: str) -> BatchTestRequestEntity | None:
        for row in self._batch_test_requests:
            if row.id == request_id:
                return row
        return None

    def run_batch_test_request(self, request_id: str) -> BatchTestRunResultEntity:
        for row in self._batch_test_requests:
            if row.id == request_id and row.status == "pending":
                row.status = "running"
                config_payload = dict(row.testDataConfig or {})
                correlation_id = str(config_payload.get("executionCorrelationId") or f"corr-{uuid4().hex[:12]}")
                config_payload["executionCorrelationId"] = correlation_id
                row.executionCorrelationId = correlation_id
                try:
                    sample_count = int(config_payload.get("sampleCount") or 10)
                    version_id = str(
                        config_payload.get("versionId")
                        or next(iter(self._version_catalog.keys()), "")
                    )
                    run_result = self.run_rule_with_generated_data(
                        row.ruleId,
                        version_id,
                        sample_count=sample_count,
                    )
                    proof = self.store_test_proof(
                        row.ruleId,
                        {
                            "coverage": float(run_result.successRate) / 100,
                            "passed": bool(run_result.failedCount == 0),
                            "recordsTestedCount": int(run_result.totalTests),
                            "failuresFound": int(run_result.failedCount),
                            "proofData": {
                                "source": "batch-test-request",
                                "requestId": request_id,
                                "testDataSource": run_result.testDataSource,
                            },
                            "executionTrace": {
                                "correlationId": correlation_id,
                            },
                        },
                    )
                    row.testDataConfig = {
                        key: value
                        for key, value in config_payload.items()
                        if key != "executionCorrelationId"
                    }
                    row.status = "completed"
                    row.completedAt = proof.testDate
                    row.proofId = proof.proofId
                except Exception as exc:
                    error_code = str(getattr(exc, "error_code", "") or "EXECUTOR_RUNTIME_ERROR")
                    runtime_correlation_id = str(getattr(exc, "correlation_id", "") or correlation_id)
                    row.testDataConfig = {
                        **{
                            key: value
                            for key, value in config_payload.items()
                            if key != "executionCorrelationId"
                        },
                        "executionFailure": {
                            "reason": "executor-runtime-error",
                            "errorType": exc.__class__.__name__,
                            "errorCode": error_code,
                            "correlationId": runtime_correlation_id,
                            "message": str(exc),
                        },
                    }
                    row.executionCorrelationId = runtime_correlation_id
                    row.status = "failed"
                    row.completedAt = "2026-03-01T00:00:00Z"
                    row.proofId = None
                break
        request_row = self.get_batch_test_request(request_id)
        return BatchTestRunResultEntity(
            id=request_id,
            status=request_row.status if request_row is not None else "running",
        )

    def list_test_proofs(self, rule_id: str) -> list[TestProofEntity]:
        rows = [row for row in self._test_proofs if row["ruleId"] == rule_id]
        sorted_rows = sorted(rows, key=lambda row: str(row["testDate"]), reverse=True)
        mapped: list[TestProofEntity] = []
        for row in sorted_rows:
            row_id = str(row.get("id") or "")
            test_date = str(row.get("testDate") or "")
            row_status = str(row.get("status") or "")
            proof_data = dict(row.get("proofData") or row.get("testData") or {})

            execution_trace = dict(
                row.get("executionTrace") or row.get("proofData", {}).get("executionTrace") or {}
            )
            execution_trace.setdefault("executionId", f"exec-{row_id}" if row_id else "")
            execution_trace.setdefault("correlationId", f"corr-{row_id}" if row_id else None)
            execution_trace.setdefault("executedAt", test_date or None)
            execution_trace.setdefault("resultStatus", row_status)

            mapped.append(
                TestProofEntity(
                    id=row_id,
                    ruleId=str(row.get("ruleId") or ""),
                    testDate=test_date,
                    coverage=float(row.get("coverage") or 0.0),
                    status=row_status,
                    recordsTestedCount=int(row.get("recordsTestedCount") or 0),
                    failuresFound=int(row.get("failuresFound") or 0),
                    proofData=proof_data,
                    executionTrace=execution_trace,
                    metrics=dict(row.get("metrics") or {}) or None,
                    diagnostics=list(row.get("diagnostics") or []) or None,
                )
            )

        return mapped
