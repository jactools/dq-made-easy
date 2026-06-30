"""
Trino Execution Pipeline Module

Orchestrates the full Trino execution pipeline.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from trino_adapter import (
    lower_aggregate_rule_to_trino,
    lower_query_rule_to_trino,
    lower_row_rule_to_trino,
    validate_trino_compatibility,
)
from trino_executor import TrinoExecutionError, TrinoExecutor

logger = logging.getLogger(__name__)


class ExecutionPlan:
    """
    Represents an execution plan for a Trino rule.
    """
    
    def __init__(
        self,
        rule: dict[str, Any],
        executor: TrinoExecutor,
        config: dict[str, Any] | None = None,
    ):
        """
        Create an execution plan.
        
        Args:
            rule: The rule to execute
            executor: TrinoExecutor instance
            config: Optional Trino config
        """
        self.rule = rule
        self.executor = executor
        self.config = config or {}
        self.plan = self._build_plan()
    
    def _build_plan(self) -> dict[str, Any]:
        """
        Build the execution plan for the rule.
        
        Returns:
            Execution plan dictionary
        """
        rule_type = self.rule.get("type") or ""
        
        # Validate compatibility
        unsupported = validate_trino_compatibility(self.rule)
        if unsupported:
            raise ValueError(f"Trino compatibility issues: {unsupported}")
        
        # Lower the rule to Trino SQL
        if rule_type == "query":
            lowered = lower_query_rule_to_trino(self.rule)
        elif rule_type in ("row_dq", "aggregate_dq"):
            if rule_type == "aggregate_dq":
                lowered = lower_aggregate_rule_to_trino(self.rule)
            else:
                lowered = lower_row_rule_to_trino(self.rule)
        else:
            raise ValueError(f"Unsupported rule type: {rule_type}")
        
        return {
            "rule_id": self.rule.get("id"),
            "rule_type": rule_type,
            "lowered_rule": lowered,
            "query": lowered["query"],
            "expectation": lowered["expectation"],
        }
    
    def execute(self) -> dict[str, Any]:
        """
        Execute the plan and return results.
        
        Returns:
            Execution result dictionary
        """
        plan = self.plan
        rule_type = plan["rule_type"]
        
        # Execute the query
        try:
            result_df = self.executor.execute_query(
                self.executor,
                plan["query"],
                timeout=self.config.get("timeout_ms", 30000),
            )
            
            # Validate the result
            validation = self._validate_result(result_df, plan)
            
            return {
                "ok": True,
                "rule_id": plan["rule_id"],
                "rule_type": rule_type,
                "result": validation,
                "metrics": self._collect_metrics(result_df, plan),
            }
            
        except TrinoExecutionError as e:
            return {
                "ok": False,
                "rule_id": plan["rule_id"],
                "rule_type": rule_type,
                "result": {
                    "passed": False,
                    "error": str(e),
                    "error_code": e.error_code,
                    "query_id": e.query_id,
                },
                "metrics": self._collect_metrics(result_df, plan),
            }
    
    def _validate_result(
        self,
        result_df: pd.DataFrame,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate query result against expectation.
        
        Args:
            result_df: Query result DataFrame
            plan: Execution plan
            
        Returns:
            Validation result
        """
        rule_type = plan["rule_type"]
        lowered_rule = plan["lowered_rule"]
        
        if rule_type == "query_dq":
            # For query DQ, we check the result count
            expected_count = None
            if "expected_count" in lowered_rule.get("params", {}):
                expected_count = lowered_rule["params"]["expected_count"]
            
            validation = self.executor.validate_query_result(
                result_df,
                {"expected_count": expected_count},
            )
            return validation
            
        elif rule_type == "aggregate_dq":
            # For aggregate DQ, we check the aggregated value
            expectation = lowered_rule["expectation"]
            
            # Extract the expected value from the expectation
            if "==" in expectation:
                expected_value_str = expectation.split("==")[1].strip()
                expected_value = float(expected_value_str) if "." in expected_value_str else int(expected_value_str)
                
                validation = self.executor.validate_query_result(
                    result_df,
                    {"expected_count": expected_value},
                )
                return validation
                
        return {
            "passed": True,
            "actual_count": len(result_df),
            "details": {},
        }
    
    def _collect_metrics(
        self,
        result_df: pd.DataFrame,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Collect execution metrics.
        
        Args:
            result_df: Query result DataFrame
            plan: Execution plan
            
        Returns:
            Metrics dictionary
        """
        return self.executor.collect_query_metrics(
            plan["query"],
            time.time(),
            len(result_df),
        )


class ExecutionResult:
    """
    Represents the result of a Trino execution pipeline.
    """
    
    def __init__(self, result: dict[str, Any], output_dir: str | None = None):
        """
        Create an execution result.
        
        Args:
            result: The execution result dictionary
            output_dir: Directory to persist artifacts
        """
        self.result = result
        self.output_dir = output_dir
        self.artifacts = self._persist_artifacts(result, output_dir)
    
    def _persist_artifacts(
        self,
        result: dict[str, Any],
        output_dir: str | None,
    ) -> list[str]:
        """
        Persist execution artifacts to disk.
        
        Args:
            result: The execution result
            output_dir: Output directory
            
        Returns:
            List of artifact file paths
        """
        artifacts = []
        
        if output_dir and self.result.get("ok"):
            try:
                os.makedirs(output_dir, exist_ok=True)
                
                # Persist rule definition
                rule_id = self.result.get("rule_id")
                if rule_id:
                    artifact_path = os.path.join(output_dir, f"{rule_id}_rule.json")
                    with open(artifact_path, "w") as f:
                        json.dump(self.result, f, indent=2)
                    artifacts.append(artifact_path)
                
                # Persist query SQL
                query = self.result.get("lowered_rule", {}).get("query")
                if query:
                    artifact_path = os.path.join(output_dir, f"{rule_id}_query.sql")
                    with open(artifact_path, "w") as f:
                        f.write(query)
                    artifacts.append(artifact_path)
                
            except Exception as e:
                logger.warning(f"Failed to persist artifacts: {e}")
        
        return artifacts
