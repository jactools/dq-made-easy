"""
Catalog Module

Business terms and alias integration with external catalogs (DataHub, OpenMetadata, Collibra, etc.)
Includes sync, resolution, validation enrichment, and governance capabilities.
"""

from .adapter import CatalogAdapter, CatalogConfig, BusinessTerm, CatalogSyncResult
from .datahub_adapter import DataHubCatalogAdapter
from .openmetadata_adapter import OpenMetadataCatalogAdapter
from .sync_service import CatalogSyncService
from .alias_resolver import AliasResolver, AliasSourceType, ResolvedAlias
from .validation_enricher import ValidationEnricher, EnrichedValidationResult, EnrichedAliasDiagnostic
from .drift_detection_service import DriftDetectionService, DriftType, TermDrift, RuleDrift, DriftSummary
from .batch_revalidation_service import BatchRevalidationService, RevalidationStatus, RuleRevalidationResult, BatchRevalidationJob

__all__ = [
    'CatalogAdapter',
    'CatalogConfig', 
    'BusinessTerm',
    'CatalogSyncResult',
    'DataHubCatalogAdapter',
    'OpenMetadataCatalogAdapter',
    'CatalogSyncService',
    'AliasResolver',
    'AliasSourceType',
    'ResolvedAlias',
    'ValidationEnricher',
    'EnrichedValidationResult',
    'EnrichedAliasDiagnostic',
    'DriftDetectionService',
    'DriftType',
    'TermDrift',
    'RuleDrift',
    'DriftSummary',
    'BatchRevalidationService',
    'RevalidationStatus',
    'RuleRevalidationResult',
    'BatchRevalidationJob',
]
