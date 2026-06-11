"""
Catalog Sync Service

Orchestrates syncing business terms from external catalog to local cache,
with error handling, logging, and health tracking.
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from .adapter import CatalogAdapter, CatalogConfig, CatalogSyncResult
from .datahub_adapter import DataHubCatalogAdapter
from .openmetadata_adapter import OpenMetadataCatalogAdapter
from ...db.models import BusinessTerm as BusinessTermModel, CatalogSyncLog

logger = logging.getLogger(__name__)


class CatalogSyncService:
    """Manages sync operations between external catalog and local database"""
    
    def __init__(self, session: AsyncSession, config: CatalogConfig):
        self.session = session
        self.config = config
        self.adapter = self._create_adapter()
    
    def _create_adapter(self) -> CatalogAdapter:
        """Factory method to create appropriate adapter based on provider"""
        if self.config.provider == 'datahub':
            return DataHubCatalogAdapter(self.config)
        if self.config.provider == 'openmetadata':
            return OpenMetadataCatalogAdapter(self.config)
        else:
            raise ValueError(f"Unknown catalog provider: {self.config.provider}")
    
    async def sync_all_terms(self) -> CatalogSyncResult:
        """
        Full sync of all catalog terms to database
        
        1. Connect to catalog
        2. Fetch all terms
        3. Calculate diffs (added, updated, removed)
        4. Upsert to database
        5. Log sync result
        """
        start_time = datetime.utcnow()
        result = CatalogSyncResult(success=False)
        
        try:
            await self.adapter.connect()
            
            # Verify health before proceeding
            is_healthy = await self.adapter.is_healthy()
            if not is_healthy:
                raise RuntimeError("Catalog is not healthy")
            
            # Fetch all current terms from database (for diff calculation)
            existing_terms = await self._get_existing_terms()
            existing_keys = {t.term_key: t for t in existing_terms}
            
            # Fetch all terms from catalog
            catalog_terms = await self.adapter.fetch_all_terms()
            
            # Calculate changes
            added = 0
            updated = 0
            catalog_keys = set()
            
            for term in catalog_terms:
                catalog_keys.add(term.term_key)
                
                if term.term_key in existing_keys:
                    # Update existing
                    existing = existing_keys[term.term_key]
                    result_updated = await self._update_term(existing, term)
                    if result_updated:
                        updated += 1
                else:
                    # Add new
                    await self._add_term(term)
                    added += 1
            
            # Find and remove deleted terms
            removed = await self._remove_deleted_terms(existing_keys, catalog_keys)
            
            # Commit all changes
            await self.session.commit()
            
            # Calculate metrics
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result = CatalogSyncResult(
                success=True,
                terms_added=added,
                terms_updated=updated,
                terms_removed=removed,
                total_processed=len(catalog_terms),
                duration_ms=duration_ms
            )
            
            logger.info(f"Catalog sync completed: +{added} ~{updated} -{removed} in {duration_ms}ms")
            
        except Exception as e:
            logger.error(f"Catalog sync failed: {e}", exc_info=True)
            await self.session.rollback()
            result.success = False
            result.errors = [str(e)]
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result.duration_ms = duration_ms
        
        finally:
            await self.adapter.disconnect()
            await self._log_sync_result(result, start_time)
        
        return result
    
    async def sync_terms_by_domain(self, domain: str) -> CatalogSyncResult:
        """Sync terms for a specific domain"""
        start_time = datetime.utcnow()
        result = CatalogSyncResult(success=False)
        
        try:
            await self.adapter.connect()
            
            catalog_terms = await self.adapter.fetch_terms_by_domain(domain)
            
            for term in catalog_terms:
                existing = await self._get_term_by_key(term.term_key)
                if existing:
                    await self._update_term(existing, term)
                else:
                    await self._add_term(term)
            
            await self.session.commit()
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            result = CatalogSyncResult(
                success=True,
                total_processed=len(catalog_terms),
                terms_added=len(catalog_terms),
                duration_ms=duration_ms
            )
            
            logger.info(f"Domain sync for '{domain}' completed: {len(catalog_terms)} terms in {duration_ms}ms")
            
        except Exception as e:
            logger.error(f"Domain sync failed: {e}")
            await self.session.rollback()
            result.errors = [str(e)]
        
        finally:
            await self.adapter.disconnect()
            await self._log_sync_result(result, start_time)
        
        return result
    
    async def get_health_status(self) -> Optional[CatalogSyncLog]:
        """Get latest sync status and health info"""
        stmt = select(CatalogSyncLog).order_by(CatalogSyncLog.completed_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_existing_terms(self):
        """Fetch all existing terms from database"""
        stmt = select(BusinessTermModel)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def _get_term_by_key(self, term_key: str) -> Optional[BusinessTermModel]:
        """Fetch a single term by key"""
        stmt = select(BusinessTermModel).where(BusinessTermModel.term_key == term_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _add_term(self, term) -> BusinessTermModel:
        """Add new term to database"""
        db_term = BusinessTermModel(
            term_key=term.term_key,
            term_name=term.term_name,
            term_description=term.description,
            data_type=term.data_type,
            domain=term.domain,
            glossary_id=term.glossary_id,
            source_system='catalog',
            catalog_metadata=term.metadata,
            last_synced=datetime.utcnow()
        )
        self.session.add(db_term)
        return db_term
    
    async def _update_term(self, db_term: BusinessTermModel, catalog_term) -> bool:
        """Update existing term if changed"""
        changed = False
        
        if db_term.term_name != catalog_term.term_name:
            db_term.term_name = catalog_term.term_name
            changed = True
        
        if db_term.term_description != catalog_term.description:
            db_term.term_description = catalog_term.description
            changed = True
        
        if db_term.data_type != catalog_term.data_type:
            db_term.data_type = catalog_term.data_type
            changed = True
        
        if db_term.domain != catalog_term.domain:
            db_term.domain = catalog_term.domain
            changed = True
        
        if db_term.catalog_metadata != catalog_term.metadata:
            db_term.catalog_metadata = catalog_term.metadata
            changed = True
        
        if changed:
            db_term.last_synced = datetime.utcnow()
        
        return changed
    
    async def _remove_deleted_terms(self, existing_keys: dict, catalog_keys: set) -> int:
        """Mark terms as removed if they no longer exist in catalog"""
        removed_count = 0
        for key in existing_keys:
            if key not in catalog_keys:
                # Option: soft delete or keep with flag
                # For now, we'll keep for audit trail
                existing_keys[key].source_system = 'deleted_from_catalog'
                removed_count += 1
        
        return removed_count
    
    async def _log_sync_result(self, result: CatalogSyncResult, start_time: datetime) -> None:
        """Log sync result to database for audit trail"""
        try:
            log_entry = CatalogSyncLog(
                sync_type='full' if result.total_processed > 0 else 'partial',
                status='success' if result.success else ('partial' if result.errors else 'failed'),
                total_terms_synced=result.total_processed,
                terms_added=result.terms_added,
                terms_updated=result.terms_updated,
                terms_removed=result.terms_removed,
                error_message='; '.join(result.errors) if result.errors else None,
                duration_ms=result.duration_ms,
                started_at=start_time,
                completed_at=datetime.utcnow()
            )
            self.session.add(log_entry)
            await self.session.commit()
        except Exception as e:
            logger.error(f"Failed to log sync result: {e}")
