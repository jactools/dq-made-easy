from __future__ import annotations
from sqlalchemy import Column, Integer, String, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.infrastructure.orm.base import Base


class ProfilingRequestModel(Base):
    __tablename__ = 'profiling_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    profiling_request_id = Column(String(64), unique=True, nullable=False, index=True)
    data_source_id = Column(String(128), nullable=True)
    requested_by_user_id = Column(String(128), nullable=True)
    requested_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default='pending')
    error_message = Column(Text, nullable=True)
    job_id = Column(String(128), nullable=True, index=True)
