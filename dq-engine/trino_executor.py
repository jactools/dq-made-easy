"""
Trino Execution Engine Module

Handles Trino query execution and result validation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from trino.dbapi import Connection
from trino.dbapi import connect
from trino.exceptions import OperationalError
from trino.exceptions import TrinoQueryError
from trino.exceptions import TrinoUserError

from trino_config import load_trino_config

logger = logging.getLogger(__name__)


@dataclass
class TrinoQueryResult:
    rows: list[Any]
    row_count: int
    truncated: bool = False

    def __len__(self) -> int:
        return self.row_count

    def __bool__(self) -> bool:
        return self.row_count > 0

    def __getitem__(self, index: int) -> Any:
        return self.rows[index]

    def __iter__(self) -> Any:
        return iter(self.rows)

    @property
    def sample_rows(self) -> list[Any]:
        return list(self.rows)


class TrinoExecutionError(Exception):
    """Exception raised when Trino query execution fails."""
    
    def __init__(self, message: str, query_id: str | None = None, error_code: str | None = None):
        self.query_id = query_id
        self.error_code = error_code
        super().__init__(f"{error_code}: {message}" if error_code else message)


class TrinoExecutor:
    """
    Execute Trino queries and collect results.
    """
    
    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the Trino executor.
        
        Args:
            config: Trino connection configuration
        """
        if config is None:
            config = load_trino_config()
        self.config = config
    
    def create_connection(self) -> Connection:
        """
        Create and configure a Trino connection.
        
        Returns:
            Configured Trino DBAPI connection
        """
        config = self.config
        return connect(
            host=config["host"],
            port=config["http_port"],
            user=config["user"],
            catalog=config["catalog"],
            schema=config["schema"],
            session_properties={
                "query_max_runtime_ms": str(config["timeout_ms"]),
                "memory_per_task": config["memory_per_task"],
                "max_row_fetch_size": config["max_row_fetch_size"],
            },
            extra_credential_headers={},
        )
    
    def execute_query(
        self,
        client: Connection,
        query: str,
        timeout: int | None = None,
    ) -> TrinoQueryResult:
        """
        Execute a Trino query and return results as a list of rows.
        
        Args:
            client: Trino client to use
            query: SQL query to execute
            timeout: Query timeout in milliseconds
            
        Returns:
            TrinoQueryResult containing a bounded sample of rows and the full row count
            
        Raises:
            TrinoExecutionError: If query execution fails
        """
        start_time = time.time()
        fetch_batch_size = max(int(self.config.get("max_row_fetch_size", 10000)), 1)
        sample_limit = max(int(self.config.get("max_result_sample_size", 1000)), 0)
        sampled_rows: list[Any] = []
        row_count = 0
        truncated = False
        
        try:
            cursor = client.cursor()
            cursor.execute(query)
            while True:
                batch = cursor.fetchmany(fetch_batch_size)
                if not batch:
                    break

                row_count += len(batch)
                if len(sampled_rows) < sample_limit:
                    remaining_slots = sample_limit - len(sampled_rows)
                    sampled_rows.extend(batch[:remaining_slots])
                    if len(batch) > remaining_slots:
                        truncated = True
                else:
                    truncated = True

            duration_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"Query executed in {duration_ms}ms, returned {row_count} rows")

            return TrinoQueryResult(rows=sampled_rows, row_count=row_count, truncated=truncated)
                
        except TrinoUserError as e:
            raise TrinoExecutionError(
                f"Trino query error: {e.message}",
                query_id=None,
                error_code="DQ_TRINO_QUERY_ERROR"
            )
        except TrinoQueryError as e:
            raise TrinoExecutionError(
                f"Trino query exception: {e}",
                query_id=None,
                error_code="DQ_TRINO_QUERY_ERROR"
            )
        except OperationalError as e:
            raise TrinoExecutionError(
                f"Trino connection error: {e}",
                query_id=None,
                error_code="DQ_TRINO_CONNECTION_FAILED"
            )
        except Exception as e:
            raise TrinoExecutionError(
                f"Query execution failed: {str(e)}",
                query_id=None,
                error_code="DQ_TRINO_EXECUTION_ERROR"
            )
    
    def validate_query_result(
        self,
        result: Any,
        expected: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate query results against expected values.
        
        Args:
            result: Query result rows or TrinoQueryResult wrapper
            expected: Dictionary with expected values
            
        Returns:
            Validation result dictionary
        """
        validation_result = {
            "passed": True,
            "actual_count": len(result),
            "expected_count": expected.get("expected_count"),
            "failed_rows": [],
            "details": {},
        }

        def _first_cell(rows: list[Any]) -> Any:
            if not rows:
                return None
            first_row = rows[0]
            if isinstance(first_row, dict):
                return next(iter(first_row.values()), None)
            if isinstance(first_row, (list, tuple)):
                return first_row[0] if first_row else None
            return first_row
        
        # Check count
        if expected.get("expected_count") is not None:
            if expected.get("treat_first_cell_as_count"):
                actual_value = _first_cell(result)
                validation_result["actual_count"] = actual_value
                if actual_value != expected["expected_count"]:
                    validation_result["passed"] = False
                    validation_result["details"]["count_mismatch"] = True
                    validation_result["details"]["actual_count"] = actual_value
                    validation_result["details"]["expected_count"] = expected["expected_count"]
            elif len(result) != expected["expected_count"]:
                validation_result["passed"] = False
                validation_result["details"]["count_mismatch"] = True
                validation_result["details"]["actual_count"] = len(result)
                validation_result["details"]["expected_count"] = expected["expected_count"]
        
        # Check for specific value validations
        # (would need to inspect result columns based on query type)
        
        return validation_result
    
    def collect_query_metrics(
        self,
        query: str,
        start_time: float,
        rows_returned: int,
    ) -> dict[str, Any]:
        """
        Collect query performance metrics.
        
        Args:
            query: The executed query
            start_time: Query start time
            rows_returned: Number of rows returned
            
        Returns:
            Metrics dictionary
        """
        duration_ms = int((time.time() - start_time) * 1000)
        
        return {
            "query_id": None,
            "start_time": start_time,
            "end_time": time.time(),
            "duration_ms": duration_ms,
            "rows_returned": rows_returned,
            "plan_nodes": None,
            "warnings": [],
        }
