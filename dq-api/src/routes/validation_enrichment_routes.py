"""
Rule Validation Endpoint with Catalog Enrichment

Extends existing rule validation with business term metadata and provenance.
"""

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ..services.catalog import ValidationEnricher, AliasResolver
from ..auth.decorators import require_role
from ..errors import APIError, NotFoundError

logger = logging.getLogger(__name__)
bp = Blueprint('validation', __name__, url_prefix='/api/v1')


@bp.route('/rules/<rule_id>/validate/enriched', methods=['POST'])
@require_role(['analyst', 'data-steward', 'admin'])
async def validate_rule_enriched(rule_id: str):
    """
    POST /api/v1/rules/{rule_id}/validate/enriched
    
    Validate a rule and enrich results with catalog metadata and provenance.
    
    Request body:
    {
      "expression": "amount > 100",
      "detectedAliases": ["amount"],
      "manualAliasMappings": {
        "amount": "attr-123"
      }
    }
    
    Response includes:
    - Original validation result (valid, unresolved_aliases, issues)
    - Diagnostics for each alias:
      - source: 'catalog', 'manual', 'unresolved'
      - resolvedTermName, resolvedDataType, domain
      - confidence level, warnings
    - Catalog health status
    - Stats: catalog-sourced vs manual vs unresolved
    """
    try:
        data = request.get_json()
        
        # Extract parameters
        rule_version_id = data.get('ruleVersionId')
        expression = data.get('expression')
        detected_aliases = data.get('detectedAliases', [])
        manual_mappings = data.get('manualAliasMappings', {})
        unresolved_aliases = data.get('unresolvedAliases', [])
        original_issues = data.get('issues', [])
        
        if not rule_version_id:
            raise APIError('ruleVersionId required', 400)
        
        # Get database session
        db: AsyncSession = current_app.db_session
        
        # Perform enrichment
        enricher = ValidationEnricher(db)
        enriched = await enricher.enrich_validation(
            rule_id=rule_id,
            rule_version_id=rule_version_id,
            is_valid=len(unresolved_aliases) == 0,
            unresolved_aliases=unresolved_aliases,
            issues=original_issues,
            manual_alias_mappings=manual_mappings,
            detected_aliases=detected_aliases,
        )
        
        # Format response
        response = enricher.format_for_response(enriched)
        
        logger.info(f"Rule {rule_id} validated with enrichment")
        
        return jsonify(response), 200
    
    except APIError as e:
        return jsonify({'error': e.message}), e.status_code
    except Exception as e:
        logger.error(f"Enriched validation failed: {e}", exc_info=True)
        raise APIError(f"Validation enrichment failed: {str(e)}", 500)


@bp.route('/aliases/resolve', methods=['POST'])
@require_role(['analyst', 'data-steward', 'admin'])
async def resolve_aliases():
    """
    POST /api/v1/aliases/resolve
    
    Resolve multiple aliases using catalog + manual mappings.
    
    Request body:
    {
      "aliases": ["amount", "customer_id"],
      "manualMappings": {
        "customer_id": "attr-456"
      }
    }
    
    Response: Dict of alias -> {source, resolvedTermName, resolvedDataType, ...}
    """
    try:
        data = request.get_json()
        aliases = data.get('aliases', [])
        manual_mappings = data.get('manualMappings', {})
        
        if not aliases:
            raise APIError('aliases array required', 400)
        
        db: AsyncSession = current_app.db_session
        resolver = AliasResolver(db)
        
        # Resolve all aliases
        resolutions = await resolver.resolve_all_aliases(aliases, manual_mappings)
        
        # Format response
        response = {
            'resolutions': {
                alias_name: {
                    'aliasName': resolved.alias_name,
                    'source': resolved.source.value,
                    'resolvedTermKey': resolved.resolved_term_key,
                    'resolvedTermName': resolved.resolved_term_name,
                    'resolvedDataType': resolved.resolved_data_type,
                    'domain': resolved.resolved_domain,
                    'confidence': resolved.confidence,
                }
                for alias_name, resolved in resolutions.items()
            }
        }
        
        return jsonify(response), 200
    
    except APIError as e:
        return jsonify({'error': e.message}), e.status_code
    except Exception as e:
        logger.error(f"Alias resolution failed: {e}", exc_info=True)
        raise APIError(f"Alias resolution failed: {str(e)}", 500)


@bp.route('/rules/<rule_id>/<rule_version_id>/alias-provenance', methods=['GET'])
@require_role(['analyst', 'data-steward', 'admin'])
async def get_alias_provenance(rule_id: str, rule_version_id: str):
    """
    GET /api/v1/rules/{rule_id}/{rule_version_id}/alias-provenance
    
    Get provenance history for all aliases in a rule version.
    Shows which aliases came from catalog vs manual.
    """
    try:
        from ...db.models import AliasSourceMetadata
        from sqlalchemy import select
        
        db: AsyncSession = current_app.db_session
        
        # Get all current alias resolutions for this rule version
        stmt = select(AliasSourceMetadata).where(
            (AliasSourceMetadata.rule_version_id == rule_version_id) &
            (AliasSourceMetadata.is_current == True)
        )
        
        result = await db.execute(stmt)
        entries = result.scalars().all()
        
        response = {
            'ruleId': rule_id,
            'ruleVersionId': rule_version_id,
            'aliasMappings': [
                {
                    'aliasName': entry.alias_name,
                    'source': entry.source_type,
                    'resolvedTermId': entry.resolved_term_id,
                    'resolvedDataType': entry.resolved_data_type,
                    'syncTimestamp': entry.sync_timestamp.isoformat() if entry.sync_timestamp else None,
                    'createdAt': entry.created_at.isoformat(),
                }
                for entry in entries
            ],
            'catalogSourcedCount': sum(1 for e in entries if e.source_type == 'catalog'),
            'manualSourcedCount': sum(1 for e in entries if e.source_type == 'manual'),
        }
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Error fetching alias provenance: {e}", exc_info=True)
        raise APIError(f"Failed to fetch provenance: {str(e)}", 500)
