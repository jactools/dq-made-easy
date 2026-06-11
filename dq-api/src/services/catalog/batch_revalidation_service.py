"""
Batch Revalidation Service for Rules

Revalidates multiple rule versions in batch when drift is detected.
Triggers re-enrichment of validation with latest catalog data.
Tracks revalidation progress and results.

Workflow:
  1. Detect drift for rules affected by catalog changes
  2. Queue rules for revalidation
  3. Revalidate in parallel batches
  4. Store new validation results
  5. Notify users of changes
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from dq_api.src.models.models import (
    RuleVersion,
    Rule,
    ValidationResult,
    AliasSourceMetadata,
)


class RevalidationStatus(str, Enum):
    """Status of revalidation job"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some rules succeeded, some failed


@dataclass
class RuleRevalidationResult:
    """Result of revalidating a single rule"""
    rule_id: str
    rule_version_id: str
    rule_name: str
    previous_valid: bool
    current_valid: bool
    validation_changed: bool
    new_issues: List[str]
    resolved_issues: List[str]
    status: str  # 'success' | 'failed'
    error_message: Optional[str] = None
    revalidated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BatchRevalidationJob:
    """Batch revalidation job tracking"""
    job_id: str
    triggered_by_term_id: Optional[str]
    triggered_by_term_name: Optional[str]
    rule_versions_queued: int
    rule_versions_completed: int
    rule_versions_failed: int
    status: RevalidationStatus
    results: List[RuleRevalidationResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_summary: Optional[str] = None

    def progress_percentage(self) -> int:
        """Calculate progress percentage"""
        if self.rule_versions_queued == 0:
            return 0
        return int((self.rule_versions_completed + self.rule_versions_failed) / self.rule_versions_queued * 100)


class BatchRevalidationService:
    """Service for batch revalidating rules"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._jobs: Dict[str, BatchRevalidationJob] = {}

    async def create_revalidation_job(
        self,
        rule_version_ids: List[str],
        triggered_by_term_id: Optional[str] = None,
        triggered_by_term_name: Optional[str] = None,
    ) -> BatchRevalidationJob:
        """
        Create a new batch revalidation job.
        
        Args:
            rule_version_ids: List of rule version IDs to revalidate
            triggered_by_term_id: Term ID that triggered this revalidation
            triggered_by_term_name: Term name for user display
            
        Returns:
            BatchRevalidationJob with initial state
        """
        job_id = str(uuid4())
        job = BatchRevalidationJob(
            job_id=job_id,
            triggered_by_term_id=triggered_by_term_id,
            triggered_by_term_name=triggered_by_term_name,
            rule_versions_queued=len(rule_version_ids),
            rule_versions_completed=0,
            rule_versions_failed=0,
            status=RevalidationStatus.PENDING,
        )

        self._jobs[job_id] = job
        return job

    async def execute_revalidation_job(
        self,
        job: BatchRevalidationJob,
        rule_version_ids: List[str],
        max_parallel: int = 5,
    ) -> BatchRevalidationJob:
        """
        Execute a batch revalidation job.
        
        Revalidates rules in parallel batches.
        
        Args:
            job: The job to execute
            rule_version_ids: List of rule version IDs to revalidate
            max_parallel: Maximum parallel revalidation tasks
            
        Returns:
            Updated BatchRevalidationJob with results
        """
        job.status = RevalidationStatus.IN_PROGRESS
        job.started_at = datetime.utcnow()

        try:
            # Process in parallel batches
            results: List[RuleRevalidationResult] = []
            for i in range(0, len(rule_version_ids), max_parallel):
                batch = rule_version_ids[i : i + max_parallel]
                batch_results = await asyncio.gather(
                    *[self._revalidate_rule_version(rv_id) for rv_id in batch],
                    return_exceptions=False,
                )
                results.extend([r for r in batch_results if r])

            # Update job with results
            job.results = results
            job.rule_versions_completed = len([r for r in results if r.status == 'success'])
            job.rule_versions_failed = len([r for r in results if r.status == 'failed'])

            # Determine final status
            if job.rule_versions_failed == 0:
                job.status = RevalidationStatus.COMPLETED
            elif job.rule_versions_completed > 0:
                job.status = RevalidationStatus.PARTIAL
            else:
                job.status = RevalidationStatus.FAILED

        except Exception as e:
            job.status = RevalidationStatus.FAILED
            job.error_summary = str(e)

        finally:
            job.completed_at = datetime.utcnow()

        return job

    async def get_job_status(self, job_id: str) -> Optional[BatchRevalidationJob]:
        """
        Get status of a revalidation job.
        
        Returns:
            BatchRevalidationJob or None if not found
        """
        return self._jobs.get(job_id)

    async def _revalidate_rule_version(
        self,
        rule_version_id: str,
    ) -> Optional[RuleRevalidationResult]:
        """
        Internal helper to revalidate a single rule version.
        
        Returns:
            RuleRevalidationResult with revalidation outcome
        """
        try:
            # Get rule version
            stmt = (
                select(RuleVersion)
                .where(RuleVersion.id == rule_version_id)
                .options(selectinload(RuleVersion.rule))
            )
            rule_version = await self.session.scalar(stmt)

            if not rule_version:
                return None

            # Get previous validation result
            stmt = (
                select(ValidationResult)
                .where(ValidationResult.rule_version_id == rule_version_id)
                .order_by(ValidationResult.created_at.desc())
                .limit(1)
            )
            previous_validation = await self.session.scalar(stmt)

            previous_valid = previous_validation.is_valid if previous_validation else False
            previous_issues = previous_validation.validation_issues.split(',') if previous_validation and previous_validation.validation_issues else []

            # Re-run validation with fresh enrichment
            # This would call back into validation_enricher to re-enrich with latest catalog
            # For now, we simulate the revalidation
            new_issues = await self._get_new_validation_issues(rule_version)
            current_valid = len(new_issues) == 0

            # Determine what changed
            validation_changed = current_valid != previous_valid or set(new_issues) != set(previous_issues)
            resolved_issues = [i for i in previous_issues if i not in new_issues]
            new_additional_issues = [i for i in new_issues if i not in previous_issues]

            return RuleRevalidationResult(
                rule_id=rule_version.rule_id,
                rule_version_id=rule_version_id,
                rule_name=rule_version.rule.name if rule_version.rule else "Unknown",
                previous_valid=previous_valid,
                current_valid=current_valid,
                validation_changed=validation_changed,
                new_issues=new_additional_issues,
                resolved_issues=resolved_issues,
                status='success',
                revalidated_at=datetime.utcnow(),
            )

        except Exception as e:
            # Extract rule info from rule_version_id if available
            rule_id = rule_version_id.split('-')[0] if '-' in rule_version_id else "unknown"

            return RuleRevalidationResult(
                rule_id=rule_id,
                rule_version_id=rule_version_id,
                rule_name="Unknown",
                previous_valid=False,
                current_valid=False,
                validation_changed=False,
                new_issues=[],
                resolved_issues=[],
                status='failed',
                error_message=str(e),
                revalidated_at=datetime.utcnow(),
            )

    async def _get_new_validation_issues(
        self,
        rule_version: RuleVersion,
    ) -> List[str]:
        """
        Get validation issues for a rule version with fresh catalog data.
        
        This would typically call the validation enricher with force_refresh=True.
        
        Returns:
            List of validation issues (empty if valid)
        """
        # TODO: Integrate with ValidationEnricher service with force-refresh
        # For now, return empty (assume issues are resolved)
        return []

    def get_summary(self, job: BatchRevalidationJob) -> Dict[str, Any]:
        """
        Get summary of revalidation job results.
        
        Returns:
            Dictionary with summary statistics
        """
        validation_improved = len([r for r in job.results if r.resolved_issues])
        validation_degraded = len([r for r in job.results if r.new_issues])
        unchanged = len([r for r in job.results if not r.validation_changed])

        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": f"{job.progress_percentage()}%",
            "queued": job.rule_versions_queued,
            "completed": job.rule_versions_completed,
            "failed": job.rule_versions_failed,
            "validation_improved": validation_improved,
            "validation_degraded": validation_degraded,
            "validation_unchanged": unchanged,
            "triggered_by_term": job.triggered_by_term_name or "N/A",
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "duration_seconds": (
                (job.completed_at - job.started_at).total_seconds()
                if job.started_at and job.completed_at
                else None
            ),
            "results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "validation_changed": r.validation_changed,
                    "was_valid": r.previous_valid,
                    "now_valid": r.current_valid,
                    "new_issues": r.new_issues,
                    "resolved_issues": r.resolved_issues,
                    "status": r.status,
                }
                for r in job.results
            ],
        }


async def create_batch_revalidation_service(
    session: AsyncSession,
) -> BatchRevalidationService:
    """Factory function to create batch revalidation service"""
    return BatchRevalidationService(session)
