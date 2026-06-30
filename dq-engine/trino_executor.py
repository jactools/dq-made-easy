"""
Trino Execution Engine Module

Handles Trino query execution and result validation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd

from trino import TrinoClient, TrinoConnectionException
from trino.exceptions import TrinoUserError, TrinoQueryException
from trino_config import load_trino_config

logger = logging.getLogger(__name__)


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
    
    def create_connection(self) -> TrinoClient:
        """
        Create and configure a Trino connection.
        
        Returns:
            Configured TrinoClient
        """
        config = self.config
        return TrinoClient(
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
        client: TrinoClient,
        query: str,
        timeout: int | None = None,
    ) -> pd.DataFrame:
        """
        Execute a Trino query and return results as DataFrame.
        
        Args:
            client: Trino client to use
            query: SQL query to execute
            timeout: Query timeout in milliseconds
            
        Returns:
            pandas DataFrame with query results
            
        Raises:
            TrinoExecutionError: If query execution fails
        """
        start_time = time.time()
        
        try:
            # Execute with timeout
            with client.query(query, max_row_fetch_size=self.config.get("max_row_fetch_size", 10000)) as query_result:
                # Handle streaming results for large queries
                rows = list(query_result.iterrows(timeout=timeout or 60))
                
                duration_ms = int((time.time() - start_time) * 1000)
                logger.debug(f"Query executed in {duration_ms}ms, returned {len(rows)} rows")
                
                return pd.DataFrame(rows)
                
        except TrinoUserError as e:
            raise TrinoExecutionError(
                f"Trino query error: {e.message}",
                query_id=None,
                error_code="DQ_TRINO_QUERY_ERROR"
            )
        except TrinoQueryException as e:
            raise TrinoExecutionError(
                f"Trino query exception: {e}",
                query_id=None,
                error_code="DQ_TRINO_QUERY_ERROR"
            )
        except TrinoConnectionException as e:
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
        result: pd.DataFrame,
        expected: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate query results against expected values.
        
        Args:
            result: Query result DataFrame
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
        
        # Check count
        if expected.get("expected_count") is not None:
            if len(result) != expected["expected_count"]:
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
