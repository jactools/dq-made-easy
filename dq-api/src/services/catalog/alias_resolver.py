"""
Alias Resolver Service

Implements alias resolution precedence:
1. Catalog terms (primary source)
2. Manual alias mappings (fallback)
3. Raw token name (final fallback)

Also tracks provenance for diagnostics.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from enum import Enum
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AliasSourceType(str, Enum):
    """Where an alias was resolved from"""
    CATALOG = "catalog"
    MANUAL = "manual"
    RAW_TOKEN = "raw_token"
    UNRESOLVED = "unresolved"


@dataclass
class ResolvedAlias:
    """Result of alias resolution"""
    alias_name: str
    resolved_term_key: Optional[str]  # Catalog term key if resolved from catalog
    resolved_term_name: Optional[str]  # Human-readable term name
    resolved_data_type: Optional[str]  # Expected data type
    resolved_domain: Optional[str]  # Business domain
    source: AliasSourceType
    confidence: float = 1.0  # 1.0 = certain, < 1.0 = fuzzy match
    metadata: Dict = None


class AliasResolver:
    """Resolves business term aliases using configured precedence"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def resolve_alias(
        self,
        alias_name: str,
        manual_mappings: Optional[Dict[str, str]] = None,
        fuzzy_match: bool = True,
    ) -> ResolvedAlias:
        """
        Resolve an alias using precedence:
        1. Catalog terms (exact + fuzzy match)
        2. Manual mappings
        3. Raw token
        
        Args:
            alias_name: The alias to resolve (e.g., "amount", "customer")
            manual_mappings: Dict of {alias_name: attribute_id}
            fuzzy_match: Allow fuzzy matching in catalog
        
        Returns:
            ResolvedAlias with source and resolved term info
        """
        # Step 1: Try exact match in catalog
        catalog_term = await self._resolve_from_catalog_exact(alias_name)
        if catalog_term:
            return ResolvedAlias(
                alias_name=alias_name,
                resolved_term_key=catalog_term.term_key,
                resolved_term_name=catalog_term.term_name,
                resolved_data_type=catalog_term.data_type,
                resolved_domain=catalog_term.domain,
                source=AliasSourceType.CATALOG,
                confidence=1.0,
                metadata={'glossary_id': catalog_term.glossary_id}
            )
        
        # Step 2: Try fuzzy match in catalog
        if fuzzy_match:
            catalog_term, confidence = await self._resolve_from_catalog_fuzzy(alias_name)
            if catalog_term and confidence >= 0.7:  # 70% confidence threshold
                return ResolvedAlias(
                    alias_name=alias_name,
                    resolved_term_key=catalog_term.term_key,
                    resolved_term_name=catalog_term.term_name,
                    resolved_data_type=catalog_term.data_type,
                    resolved_domain=catalog_term.domain,
                    source=AliasSourceType.CATALOG,
                    confidence=confidence,
                    metadata={'glossary_id': catalog_term.glossary_id, 'fuzzy': True}
                )
        
        # Step 3: Check manual mappings
        if manual_mappings and alias_name in manual_mappings:
            attribute_id = manual_mappings[alias_name]
            return ResolvedAlias(
                alias_name=alias_name,
                resolved_term_key=attribute_id,  # Use attribute ID as key
                resolved_term_name=attribute_id,  # Will be looked up elsewhere
                resolved_data_type=None,
                resolved_domain=None,
                source=AliasSourceType.MANUAL,
                confidence=1.0,
                metadata={'attribute_id': attribute_id}
            )
        
        # Step 4: Unresolved
        return ResolvedAlias(
            alias_name=alias_name,
            resolved_term_key=None,
            resolved_term_name=None,
            resolved_data_type=None,
            resolved_domain=None,
            source=AliasSourceType.UNRESOLVED,
            confidence=0.0,
            metadata=None
        )
    
    async def resolve_all_aliases(
        self,
        alias_names: list,
        manual_mappings: Optional[Dict[str, str]] = None,
    ) -> Dict[str, ResolvedAlias]:
        """
        Resolve multiple aliases at once.
        
        Returns dict mapping alias_name -> ResolvedAlias
        """
        results = {}
        for alias_name in alias_names:
            results[alias_name] = await self.resolve_alias(alias_name, manual_mappings)
        return results
    
    async def _resolve_from_catalog_exact(self, alias_name: str):
        """Try exact match in catalog terms"""
        try:
            from ...db.models import BusinessTerm
            
            # Try exact match on term name (case-insensitive)
            stmt = select(BusinessTerm).where(
                BusinessTerm.term_name.ilike(alias_name)
            ).limit(1)
            
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.warning(f"Error resolving catalog exact match for '{alias_name}': {e}")
            return None
    
    async def _resolve_from_catalog_fuzzy(self, alias_name: str) -> Tuple[Optional, float]:
        """
        Try fuzzy matching in catalog terms.
        
        Uses string similarity (Levenshtein) if available, else approximate.
        
        Returns (term, confidence_score)
        """
        try:
            from ...db.models import BusinessTerm
            
            # Fetch all terms (in production, consider caching)
            stmt = select(BusinessTerm).limit(1000)
            result = await self.session.execute(stmt)
            terms = result.scalars().all()
            
            best_match = None
            best_score = 0.0
            
            for term in terms:
                # Simple similarity: check if alias is substring or similar
                score = self._string_similarity(
                    alias_name.lower(),
                    term.term_name.lower()
                )
                
                if score > best_score:
                    best_score = score
                    best_match = term
            
            # Return only if confidence > 70%
            if best_score >= 0.7:
                return best_match, best_score
            
            return None, 0.0
        
        except Exception as e:
            logger.warning(f"Error resolving catalog fuzzy match for '{alias_name}': {e}")
            return None, 0.0
    
    @staticmethod
    def _string_similarity(s1: str, s2: str) -> float:
        """Simple string similarity (0.0 to 1.0)"""
        if s1 == s2:
            return 1.0
        
        # Check if one is substring of other
        if s1 in s2 or s2 in s1:
            return 0.8
        
        # Levenshtein-like approach (simple version)
        # Count matching characters
        common = sum(1 for i, c in enumerate(s1) if i < len(s2) and c == s2[i])
        max_len = max(len(s1), len(s2))
        
        if max_len == 0:
            return 1.0
        
        return common / max_len
