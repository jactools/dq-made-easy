"""
Catalog Adapter Interface

Abstract base class defining the contract for catalog integrations
(DataHub, OpenMetadata, Collibra, Informatica).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class BusinessTerm:
    """Represents a business term from the catalog"""
    term_key: str  # Unique identifier from source catalog
    term_name: str
    description: Optional[str] = None
    data_type: Optional[str] = None
    domain: Optional[str] = None
    glossary_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # Additional catalog metadata


@dataclass
class CatalogConfig:
    """Configuration for catalog connection"""
    provider: str  # 'datahub', 'openmetadata', 'collibra', 'informatica'
    endpoint: str  # API endpoint URL
    api_key: str  # Authentication token/key
    timeout: int = 30  # Request timeout in seconds
    retry_attempts: int = 3
    batch_size: int = 100  # Terms per fetch


@dataclass
class CatalogSyncResult:
    """Result of a catalog sync operation"""
    success: bool
    terms_added: int = 0
    terms_updated: int = 0
    terms_removed: int = 0
    total_processed: int = 0
    errors: List[str] = None
    duration_ms: int = 0
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class CatalogAdapter(ABC):
    """Abstract base class for catalog adapters"""
    
    def __init__(self, config: CatalogConfig):
        self.config = config
        self.connected = False
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to catalog"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to catalog"""
        pass
    
    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check catalog health and connectivity"""
        pass
    
    @abstractmethod
    async def fetch_all_terms(self) -> List[BusinessTerm]:
        """Fetch all business terms from catalog"""
        pass
    
    @abstractmethod
    async def fetch_terms_by_domain(self, domain: str) -> List[BusinessTerm]:
        """Fetch terms filtered by domain"""
        pass
    
    @abstractmethod
    async def search_terms(self, query: str) -> List[BusinessTerm]:
        """Search terms by name or keyword"""
        pass
    
    @abstractmethod
    async def get_term_details(self, term_key: str) -> Optional[BusinessTerm]:
        """Get detailed information for a specific term"""
        pass
