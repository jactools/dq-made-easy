from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ProfilingRequest:
    id: Optional[int]
    profiling_request_id: str
    data_source_id: Optional[str]
    requested_by_user_id: Optional[str]
    requested_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    status: str
    error_message: Optional[str]
    job_id: Optional[str]
