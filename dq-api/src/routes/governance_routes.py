"""
Governance API Routes

REST endpoints for drift detection and batch revalidation.

Endpoints:
  - GET /api/v1/governance/drift/rules/{rule_id}/{version_id}
  - GET /api/v1/governance/drift/summary
  - POST /api/v1/governance/revalidation/jobs
  - GET /api/v1/governance/revalidation/jobs/{job_id}
  - POST /api/v1/governance/revalidation/jobs/{job_id}/cancel
"""

from flask import Blueprint, request, jsonify
from typing import Optional
import logging

from dq_api.src.middleware.auth_middleware import require_role
from dq_api.src.services.catalog.drift_detection_service import (
    DriftDetectionService,
    DriftType,
    create_drift_detection_service,
)
from dq_api.src.services.catalog.batch_revalidation_service import (
    BatchRevalidationService,
    create_batch_revalidation_service,
)
from dq_api.src.database.db import get_session

logger = logging.getLogger(__name__)

governance_bp = Blueprint('governance', __name__, url_prefix='/api/v1/governance')


@governance_bp.route('/drift/rules/<rule_id>/<version_id>', methods=['GET'])
@require_role('analyst')
async def check_rule_drift(rule_id: str, version_id: str):
    """
    Check drift for a specific rule version.
    
    Returns drift information for a rule that was potentially affected by
    catalog term definition changes.
    
    Args:
        rule_id: Rule ID
        version_id: Rule version ID
        
    Returns:
        JSON with RuleDrift info or 204 if no drift
    """
    try:
        async with await get_session() as session:
            drift_service = await create_drift_detection_service(session)
            rule_drift = await drift_service.detect_drift_for_rule(rule_id, version_id)

            if not rule_drift:
                return jsonify({"message": "No drift detected"}), 204

            return jsonify({
                "ruleId": rule_drift.rule_id,
                "ruleName": rule_drift.rule_name,
                "ruleVersionId": rule_drift.rule_version_id,
                "versionNumber": rule_drift.version_number,
                "affectedAliases": rule_drift.affected_aliases,
                "drifts": [
                    {
                        "driftType": d.drift_type.value,
                        "aliasName": d.alias_name,
                        "resolvedTermName": d.resolved_term_name,
                        "previousValue": d.previous_value,
                        "currentValue": d.current_value,
                        "severity": d.severity,
                        "detectedAt": d.change_detected_at.isoformat(),
                    }
                    for d in rule_drift.drifts
                ],
                "totalDrifts": rule_drift.total_drift_count,
                "needsRevalidation": rule_drift.needs_revalidation,
                "lastValidatedAt": rule_drift.last_validated_at.isoformat() if rule_drift.last_validated_at else None,
                "detectedAt": rule_drift.drift_detected_at.isoformat(),
            }), 200

    except Exception as e:
        logger.error(f"Error checking rule drift: {e}")
        return jsonify({"error": str(e)}), 500


@governance_bp.route('/drift/summary', methods=['GET'])
@require_role('analyst')
async def get_drift_summary():
    """
    Get overall drift summary for workspace.
    
    Returns aggregate drift statistics and list of affected rules.
    
    Returns:
        JSON with DriftSummary info
    """
    try:
        async with await get_session() as session:
            drift_service = await create_drift_detection_service(session)
            summary = await drift_service.get_drift_summary_for_workspace()

            return jsonify({
                "totalRulesChecked": summary.total_rules_checked,
                "rulesWithDrift": summary.rules_with_drift,
                "totalDriftsDetected": summary.total_drifts_detected,
                "criticalDrifts": summary.critical_drifts,
                "warningDrifts": summary.warning_drifts,
                "byDriftType": summary.by_drift_type,
                "affectedRules": [
                    {
                        "ruleId": r.rule_id,
                        "ruleName": r.rule_name,
                        "ruleVersionId": r.rule_version_id,
                        "versionNumber": r.version_number,
                        "affectedAliases": r.affected_aliases,
                        "totalDrifts": r.total_drift_count,
                        "needsRevalidation": r.needs_revalidation,
                    }
                    for r in summary.affected_rules
                ],
            }), 200

    except Exception as e:
        logger.error(f"Error getting drift summary: {e}")
        return jsonify({"error": str(e)}), 500


@governance_bp.route('/revalidation/jobs', methods=['POST'])
@require_role('analyst')
async def create_revalidation_job():
    """
    Create and start a batch revalidation job.
    
    Revalidates multiple rule versions when drift is detected.
    
    Request body:
        {
            "ruleVersionIds": ["v1", "v2", ...],
            "triggeredByTermId": "term-123",
            "triggeredByTermName": "amount"
        }
        
    Returns:
        JSON with BatchRevalidationJob info and job_id
    """
    try:
        data = request.get_json() or {}
        rule_version_ids = data.get('ruleVersionIds', [])
        triggered_by_term_id = data.get('triggeredByTermId')
        triggered_by_term_name = data.get('triggeredByTermName')

        if not rule_version_ids:
            return jsonify({"error": "ruleVersionIds required"}), 400

        async with await get_session() as session:
            revalidation_service = await create_batch_revalidation_service(session)

            # Create job
            job = await revalidation_service.create_revalidation_job(
                rule_version_ids=rule_version_ids,
                triggered_by_term_id=triggered_by_term_id,
                triggered_by_term_name=triggered_by_term_name,
            )

            # Execute job asynchronously
            # In production, this would be queued to a background task runner
            import asyncio
            asyncio.create_task(
                revalidation_service.execute_revalidation_job(job, rule_version_ids)
            )

            return jsonify({
                "jobId": job.job_id,
                "status": job.status.value,
                "ruleVersionsQueued": job.rule_versions_queued,
                "triggeredByTerm": job.triggered_by_term_name or "N/A",
                "startedAt": job.started_at.isoformat() if job.started_at else None,
            }), 201

    except Exception as e:
        logger.error(f"Error creating revalidation job: {e}")
        return jsonify({"error": str(e)}), 500


@governance_bp.route('/revalidation/jobs/<job_id>', methods=['GET'])
@require_role('analyst')
async def get_revalidation_job_status(job_id: str):
    """
    Get status of a batch revalidation job.
    
    Args:
        job_id: Revalidation job ID
        
    Returns:
        JSON with BatchRevalidationJob status and progress
    """
    try:
        async with await get_session() as session:
            revalidation_service = await create_batch_revalidation_service(session)
            job = await revalidation_service.get_job_status(job_id)

            if not job:
                return jsonify({"error": "Job not found"}), 404

            summary = await revalidation_service.get_summary(job)
            return jsonify(summary), 200

    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        return jsonify({"error": str(e)}), 500


@governance_bp.route('/drift/terms/<term_id>/affected-rules', methods=['GET'])
@require_role('analyst')
async def get_rules_affected_by_term(term_id: str):
    """
    Get all rules affected by changes to a specific term.
    
    Args:
        term_id: Business term ID
        
    Returns:
        JSON with list of affected RuleDrift objects
    """
    try:
        async with await get_session() as session:
            drift_service = await create_drift_detection_service(session)
            affected_rules = await drift_service.batch_detect_drift_for_term(term_id)

            return jsonify({
                "termId": term_id,
                "affectedRulesCount": len(affected_rules),
                "affectedRules": [
                    {
                        "ruleId": r.rule_id,
                        "ruleName": r.rule_name,
                        "ruleVersionId": r.rule_version_id,
                        "versionNumber": r.version_number,
                        "affectedAliases": r.affected_aliases,
                        "drifts": [
                            {
                                "driftType": d.drift_type.value,
                                "severity": d.severity,
                                "previousValue": d.previous_value,
                                "currentValue": d.current_value,
                            }
                            for d in r.drifts
                        ],
                        "totalDrifts": r.total_drift_count,
                        "needsRevalidation": r.needs_revalidation,
                    }
                    for r in affected_rules
                ],
            }), 200

    except Exception as e:
        logger.error(f"Error getting affected rules: {e}")
        return jsonify({"error": str(e)}), 500


def register_governance_routes(app):
    """Register governance routes with Flask app"""
    app.register_blueprint(governance_bp)
