"""
Validation Enrichment Service

Enriches rule validation results with:
- Catalog metadata (datatypes, domains)
- Provenance tracking (Catalog vs Manual source)
- Diagnostic information for end users
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from .alias_resolver import AliasResolver, ResolvedAlias, AliasSourceType
from ...db.models import AliasSourceMetadata

logger = logging.getLogger(__name__)


@dataclass
class EnrichedAliasDiagnostic:
    """Diagnostic info for a single alias in validation result"""
    alias_name: str
    resolution_status: str  # 'resolved' | 'unresolved' | 'fuzzy_match'
    source: str  # 'catalog' | 'manual' | 'unresolved'
    resolved_term_name: Optional[str] = None
    resolved_term_key: Optional[str] = None
    resolved_data_type: Optional[str] = None
    domain: Optional[str] = None
    glossary_id: Optional[str] = None
    confidence: float = 1.0
    warning: Optional[str] = None  # 'fuzzy_match' | 'unresolved'
    suggestion: Optional[str] = None  # For unresolved, suggest similar term


@dataclass
class EnrichedValidationResult:
    """Validation result enhanced with provenance and diagnostics"""
    # Original validation data
    rule_id: str
    rule_version_id: str
    is_valid: bool
    unresolved_aliases: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    
    # Enrichment data
    alias_diagnostics: Dict[str, EnrichedAliasDiagnostic] = field(default_factory=dict)
    catalog_available: bool = True
    last_sync: Optional[datetime] = None
    
    @property
    def catalog_sourced_aliases(self) -> List[str]:
        """Aliases resolved from catalog"""
        return [
            a for a, d in self.alias_diagnostics.items()
            if d.source == 'catalog'
        ]
    
    @property
    def manual_sourced_aliases(self) -> List[str]:
        """Aliases resolved from manual mapping"""
        return [
            a for a, d in self.alias_diagnostics.items()
            if d.source == 'manual'
        ]
    
    @property
    def unresolved_count(self) -> int:
        """Count of unresolved aliases"""
        return len(self.unresolved_aliases)


class ValidationEnricher:
    """Enriches rule validation with catalog metadata and provenance"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.alias_resolver = AliasResolver(session)
    
    async def enrich_validation(
        self,
        rule_id: str,
        rule_version_id: str,
        is_valid: bool,
        unresolved_aliases: List[str],
        issues: List[str],
        manual_alias_mappings: Optional[Dict[str, str]] = None,
        detected_aliases: Optional[List[str]] = None,  # All aliases in rule
    ) -> EnrichedValidationResult:
        """
        Enrich a validation result with catalog metadata and provenance.
        
        Args:
            rule_id: Rule identifier
            rule_version_id: Rule version identifier
            is_valid: Original validation status
            unresolved_aliases: Aliases that didn't map to attributes
            issues: Original validation issues
            manual_alias_mappings: User-provided alias mappings
            detected_aliases: All aliases detected in rule expression
        
        Returns:
            EnrichedValidationResult with diagnostics
        """
        # Determine which aliases to diagnose
        aliases_to_check = detected_aliases or unresolved_aliases or []
        
        # Get catalog health
        catalog_available, last_sync = await self._check_catalog_health()
        
        # Create diagnostics for all aliases
        alias_diagnostics = {}
        for alias_name in aliases_to_check:
            diagnostic = await self._create_alias_diagnostic(
                alias_name,
                unresolved_aliases,
                manual_alias_mappings or {},
                catalog_available
            )
            alias_diagnostics[alias_name] = diagnostic
        
        # Build enriched result
        enriched = EnrichedValidationResult(
            rule_id=rule_id,
            rule_version_id=rule_version_id,
            is_valid=is_valid,
            unresolved_aliases=unresolved_aliases,
            issues=issues,
            alias_diagnostics=alias_diagnostics,
            catalog_available=catalog_available,
            last_sync=last_sync,
        )
        
        # Log provenance to database
        await self._log_alias_provenance(rule_version_id, enriched)
        
        return enriched
    
    async def _create_alias_diagnostic(
        self,
        alias_name: str,
        unresolved_aliases: List[str],
        manual_mappings: Dict[str, str],
        catalog_available: bool,
    ) -> EnrichedAliasDiagnostic:
        """Create diagnostic for single alias"""
        
        # Resolve the alias
        resolved = await self.alias_resolver.resolve_alias(
            alias_name,
            manual_mappings,
            fuzzy_match=catalog_available
        )
        
        # Determine status and warnings
        is_unresolved = alias_name in unresolved_aliases
        is_fuzzy = resolved.metadata and resolved.metadata.get('fuzzy', False)
        
        if resolved.source == AliasSourceType.UNRESOLVED:
            status = 'unresolved'
            warning = 'unresolved'
        elif is_fuzzy:
            status = 'fuzzy_match'
            warning = 'fuzzy_match'
        else:
            status = 'resolved'
            warning = None
        
        # Create diagnostic
        diagnostic = EnrichedAliasDiagnostic(
            alias_name=alias_name,
            resolution_status=status,
            source=resolved.source.value,
            resolved_term_name=resolved.resolved_term_name,
            resolved_term_key=resolved.resolved_term_key,
            resolved_data_type=resolved.resolved_data_type,
            domain=resolved.resolved_domain,
            glossary_id=resolved.metadata.get('glossary_id') if resolved.metadata else None,
            confidence=resolved.confidence,
            warning=warning,
            suggestion=None,  # TODO: Suggest similar term if unresolved
        )
        
        return diagnostic
    
    async def _check_catalog_health(self) -> tuple:
        """Check if catalog is healthy and get last sync time"""
        try:
            from ...db.models import CatalogSyncLog
            from sqlalchemy import select, desc
            
            stmt = select(CatalogSyncLog).order_by(desc(CatalogSyncLog.completed_at)).limit(1)
            result = await self.session.execute(stmt)
            latest_sync = result.scalar_one_or_none()
            
            if latest_sync is None:
                return False, None
            
            is_healthy = latest_sync.status == 'success'
            return is_healthy, latest_sync.completed_at
        
        except Exception as e:
            logger.warning(f"Error checking catalog health: {e}")
            return False, None
    
    async def _log_alias_provenance(
        self,
        rule_version_id: str,
        enriched: EnrichedValidationResult,
    ) -> None:
        """Record alias resolution provenance to database"""
        try:
            # For each resolved alias, log source
            for alias_name, diagnostic in enriched.alias_diagnostics.items():
                # Mark previous resolution as not current
                stmt = AliasSourceMetadata.__table__.update().where(
                    (AliasSourceMetadata.rule_version_id == rule_version_id) &
                    (AliasSourceMetadata.alias_name == alias_name) &
                    (AliasSourceMetadata.is_current == True)
                ).values(is_current=False)
                
                await self.session.execute(stmt)
                
                # Add new resolution record
                if diagnostic.source != 'unresolved':
                    source_type = diagnostic.source
                    entry = AliasSourceMetadata(
                        rule_version_id=rule_version_id,
                        alias_name=alias_name,
                        source_type=source_type,
                        resolved_term_id=diagnostic.resolved_term_key,
                        resolved_data_type=diagnostic.resolved_data_type,
                        sync_timestamp=enriched.last_sync,
                        is_current=True,
                    )
                    self.session.add(entry)
            
            await self.session.commit()
        
        except Exception as e:
            logger.error(f"Error logging alias provenance: {e}")
            await self.session.rollback()
    
    def format_for_response(
        self,
        enriched: EnrichedValidationResult,
    ) -> Dict:
        """Format enriched result for API response"""
        return {
            'ruleId': enriched.rule_id,
            'ruleVersionId': enriched.rule_version_id,
            'isValid': enriched.is_valid,
            'unresolvedAliases': enriched.unresolved_aliases,
            'issues': enriched.issues,
            'diagnostics': {
                alias_name: {
                    'resolutionStatus': d.resolution_status,
                    'source': d.source,
                    'resolvedTermName': d.resolved_term_name,
                    'resolvedDataType': d.resolved_data_type,
                    'domain': d.domain,
                    'confidence': d.confidence,
                    'warning': d.warning,
                }
                for alias_name, d in enriched.alias_diagnostics.items()
            },
            'catalogAvailable': enriched.catalog_available,
            'lastSync': enriched.last_sync.isoformat() if enriched.last_sync else None,
            'stats': {
                'catalogSourcedAliases': len(enriched.catalog_sourced_aliases),
                'manualSourcedAliases': len(enriched.manual_sourced_aliases),
                'unresolvedCount': enriched.unresolved_count,
            }
        }
