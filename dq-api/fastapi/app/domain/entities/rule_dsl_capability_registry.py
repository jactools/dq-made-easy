from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RuleDslCapabilityTarget = Literal["gx", "sodacl", "soda", "sql", "pyspark_native", "spark_expectations", "trino", "custom_worker"]