"""
Catalog API Endpoints (Flask)

Routes for catalog health, term fetching, and sync operations.
"""

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import asyncio

from ..db.models import BusinessTerm, CatalogSyncLog
from ..services.catalog import CatalogSyncService, CatalogConfig
from ..auth.decorators import require_role
from ..errors import APIError, NotFoundError

bp = Blueprint('catalog', __name__, url_prefix='/api/v1/catalog')


@bp.route('/health', methods=['GET'])
async def catalog_health():
    """
    GET /api/v1/catalog/health
    
    Returns latest catalog sync status and health information.
    No authentication required (internal health check).
    """
    try:
        db = current_app.db_session
        
        # Get latest sync log
        stmt = select(CatalogSyncLog).order_by(CatalogSyncLog.completed_at.desc()).limit(1)
        result = await db.execute(stmt)
        latest_sync = result.scalar_one_or_none()
        
        # Count cached terms
        stmt_terms = select(CatalogSyncLog).func.count()
        result_terms = await db.execute(select(BusinessTerm).func.count())
        term_count = result_terms.scalar()
        
        if latest_sync is None:
            return jsonify({
                'status': 'unknown',
                'term_count': 0,
                'last_sync': None,
                'message': 'No sync has been performed yet'
            }), 200
        
        is_healthy = latest_sync.status == 'success'
        
        return jsonify({
            'status': 'healthy' if is_healthy else 'degraded',
            'last_sync': latest_sync.completed_at.isoformat(),
            'last_sync_status': latest_sync.status,
            'term_count': term_count,
            'duration_ms': latest_sync.duration_ms,
            'sync_errors': latest_sync.error_message,
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Catalog health check failed: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@bp.route('/terms', methods=['GET'])
@require_role(['analyst', 'data-steward', 'admin'])
async def get_catalog_terms():
    """
    GET /api/v1/catalog/terms?domain=...&search=...
    
    Fetch cached business terms from database with optional filtering.
    """
    try:
        db = current_app.db_session
        domain = request.args.get('domain')
        search_query = request.args.get('search')
        
        stmt = select(BusinessTerm)
        
        if domain:
            stmt = stmt.where(BusinessTerm.domain == domain)
        
        if search_query:
            stmt = stmt.where(
                BusinessTerm.term_name.ilike(f'%{search_query}%')
                | BusinessTerm.term_description.ilike(f'%{search_query}%')
            )
        
        result = await db.execute(stmt.limit(500))
        terms = result.scalars().all()
        
        return jsonify({
            'terms': [
                {
                    'termKey': t.term_key,
                    'termName': t.term_name,
                    'description': t.term_description,
                    'dataType': t.data_type,
                    'domain': t.domain,
                    'glossaryId': t.glossary_id,
                    'lastSynced': t.last_synced.isoformat() if t.last_synced else None,
                }
                for t in terms
            ],
            'count': len(terms),
            'lastSynced': datetime.utcnow().isoformat(),
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to fetch catalog terms: {e}")
        raise APIError(f"Failed to fetch terms: {str(e)}", 500)


@bp.route('/sync', methods=['POST'])
@require_role(['admin'])
async def trigger_catalog_sync():
    """
    POST /api/v1/catalog/sync
    
    Manually trigger a full sync from external catalog.
    Admin only.
    """
    try:
        # Get catalog config from app settings
        catalog_config = get_catalog_config(current_app)
        if not catalog_config:
            return jsonify({
                'error': 'Catalog not configured'
            }), 400
        
        # Create sync service and perform sync
        db = current_app.db_session
        sync_service = CatalogSyncService(db, catalog_config)
        
        # Run sync asynchronously
        result = await sync_service.sync_all_terms()
        
        return jsonify({
            'success': result.success,
            'termsAdded': result.terms_added,
            'termsUpdated': result.terms_updated,
            'termsRemoved': result.terms_removed,
            'totalProcessed': result.total_processed,
            'durationMs': result.duration_ms,
            'errors': result.errors if result.errors else None,
        }), 200 if result.success else 207
    
    except Exception as e:
        current_app.logger.error(f"Catalog sync failed: {e}")
        raise APIError(f"Sync failed: {str(e)}", 500)


@bp.route('/sync-status', methods=['GET'])
@require_role(['analyst', 'data-steward', 'admin'])
async def get_catalog_sync_status():
    """
    GET /api/v1/catalog/sync-status
    
    Get latest catalog sync status with detailed metrics.
    """
    try:
        db = current_app.db_session
        
        stmt = select(CatalogSyncLog).order_by(CatalogSyncLog.completed_at.desc()).limit(10)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        
        latest = logs[0] if logs else None
        
        return jsonify({
            'latest': {
                'startedAt': latest.started_at.isoformat(),
                'completedAt': latest.completed_at.isoformat(),
                'status': latest.status,
                'totalTermsSynced': latest.total_terms_synced,
                'termsAdded': latest.terms_added,
                'termsUpdated': latest.terms_updated,
                'termsRemoved': latest.terms_removed,
                'durationMs': latest.duration_ms,
                'errorMessage': latest.error_message,
            } if latest else None,
            'recentHistory': [
                {
                    'startedAt': log.started_at.isoformat(),
                    'completedAt': log.completed_at.isoformat(),
                    'status': log.status,
                    'termsAdded': log.terms_added,
                    'durationMs': log.duration_ms,
                }
                for log in logs
            ],
        }), 200
    
    except Exception as e:
        current_app.logger.error(f"Failed to get sync status: {e}")
        raise APIError(f"Failed to get sync status: {str(e)}", 500)


def get_catalog_config(app) -> CatalogConfig:
    """Extract catalog config from app settings"""
    try:
        provider = app.config.get('CATALOG_PROVIDER')
        endpoint = app.config.get('CATALOG_ENDPOINT')
        api_key = app.config.get('CATALOG_API_KEY')
        
        if not all([provider, endpoint, api_key]):
            return None
        
        return CatalogConfig(
            provider=provider,
            endpoint=endpoint,
            api_key=api_key,
            timeout=app.config.get('CATALOG_TIMEOUT_SECONDS', 30),
            retry_attempts=app.config.get('CATALOG_RETRY_ATTEMPTS', 3),
            batch_size=app.config.get('CATALOG_BATCH_SIZE', 100),
        )
    except Exception as e:
        app.logger.error(f"Failed to create catalog config: {e}")
        return None
