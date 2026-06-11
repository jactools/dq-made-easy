"""
OpenMetadata Catalog Adapter

Implementation of CatalogAdapter for integration with OpenMetadata
(https://open-metadata.org/).
"""

import aiohttp
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .adapter import BusinessTerm, CatalogAdapter, CatalogConfig

logger = logging.getLogger(__name__)


class OpenMetadataCatalogAdapter(CatalogAdapter):
    """OpenMetadata adapter using REST API."""

    def __init__(self, config: CatalogConfig):
        if config.provider != 'openmetadata':
            raise ValueError(
                f"OpenMetadataCatalogAdapter requires provider='openmetadata', got '{config.provider}'"
            )
        super().__init__(config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_endpoint = config.endpoint.rstrip('/')

    async def connect(self) -> None:
        """Establish HTTP session to OpenMetadata."""
        try:
            self.session = aiohttp.ClientSession(
                headers={
                    'Authorization': f'Bearer {self.config.api_key}',
                    'Content-Type': 'application/json',
                }
            )
            await self.is_healthy()
            self.connected = True
            logger.info(f"Connected to OpenMetadata at {self.config.endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to OpenMetadata: {e}")
            raise

    async def disconnect(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.connected = False
            logger.info("Disconnected from OpenMetadata")

    async def is_healthy(self) -> bool:
        """Check OpenMetadata health using common health/version endpoints."""
        if not self.session:
            return False

        candidates = [
            f"{self.base_endpoint}/api/v1/system/version",
            f"{self.base_endpoint}/healthcheck",
            f"{self.base_endpoint}/health",
        ]

        for url in candidates:
            try:
                async with self.session.get(url, timeout=self.config.timeout) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                continue

        return False

    async def fetch_all_terms(self) -> List[BusinessTerm]:
        """Fetch all glossary terms from OpenMetadata with cursor pagination."""
        terms: List[BusinessTerm] = []
        after: Optional[str] = None

        while True:
            params: Dict[str, Any] = {
                'limit': self.config.batch_size,
                'fields': 'description,tags,owners,domain,glossary,extension',
            }
            if after:
                params['after'] = after

            payload = await self._get_json('/api/v1/glossaryTerms', params=params)
            entities = (payload or {}).get('data', []) or []

            for entity in entities:
                parsed = self._parse_entity_to_term(entity)
                if parsed:
                    terms.append(parsed)

            paging = (payload or {}).get('paging', {}) or {}
            after = paging.get('after')
            if not after:
                break

        logger.info(f"Fetched {len(terms)} terms from OpenMetadata")
        return terms

    async def fetch_terms_by_domain(self, domain: str) -> List[BusinessTerm]:
        """Fetch terms and filter by domain/fqn/displayName."""
        all_terms = await self.fetch_all_terms()
        target = str(domain or '').strip().lower()
        if not target:
            return all_terms

        return [
            term
            for term in all_terms
            if str(term.domain or '').strip().lower() == target
        ]

    async def search_terms(self, query: str) -> List[BusinessTerm]:
        """Search terms by name/description with in-memory filtering."""
        all_terms = await self.fetch_all_terms()
        q = str(query or '').strip().lower()
        if not q:
            return all_terms

        matches: List[BusinessTerm] = []
        for term in all_terms:
            name = str(term.term_name or '').lower()
            description = str(term.description or '').lower()
            if q in name or q in description:
                matches.append(term)
        return matches

    async def get_term_details(self, term_key: str) -> Optional[BusinessTerm]:
        """Fetch a single glossary term by id."""
        if not term_key:
            return None

        payload = await self._get_json(
            f"/api/v1/glossaryTerms/{term_key}",
            params={'fields': 'description,tags,owners,domain,glossary,extension'},
        )
        if not payload:
            return None
        return self._parse_entity_to_term(payload)

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute a GET request against OpenMetadata API and return JSON."""
        if not self.session:
            raise RuntimeError('Not connected to OpenMetadata')

        url = f"{self.base_endpoint}{path}"
        try:
            async with self.session.get(url, params=params, timeout=self.config.timeout) as resp:
                if resp.status == 200:
                    return await resp.json()

                body = await resp.text()
                logger.warning(f"OpenMetadata API error: {resp.status} path={path} body={body[:200]}")
                return None
        except Exception as e:
            logger.error(f"OpenMetadata request failed for {path}: {e}")
            raise

    def _parse_entity_to_term(self, entity: Dict[str, Any]) -> Optional[BusinessTerm]:
        """Convert OpenMetadata glossary term payload to BusinessTerm."""
        try:
            term_id = str(entity.get('id') or '')
            term_name = (
                entity.get('displayName')
                or entity.get('name')
                or entity.get('fullyQualifiedName')
                or ''
            )
            if not term_id or not term_name:
                return None

            description = entity.get('description')
            if isinstance(description, dict):
                description = description.get('message') or description.get('text')

            domain_obj = entity.get('domain') or {}
            glossary_obj = entity.get('glossary') or {}
            extension = entity.get('extension') or {}

            domain = (
                domain_obj.get('displayName')
                or domain_obj.get('name')
                or domain_obj.get('fullyQualifiedName')
            )
            glossary_id = glossary_obj.get('id') or glossary_obj.get('fullyQualifiedName')

            data_type = None
            if isinstance(extension, dict):
                data_type = (
                    extension.get('dataType')
                    or extension.get('datatype')
                    or extension.get('type')
                )

            tags = []
            for tag in entity.get('tags') or []:
                tag_ref = tag.get('tagFQN') or tag.get('name')
                if tag_ref:
                    tags.append(tag_ref)

            return BusinessTerm(
                term_key=term_id,
                term_name=str(term_name),
                description=str(description) if description else None,
                data_type=str(data_type) if data_type else None,
                domain=str(domain) if domain else None,
                glossary_id=str(glossary_id) if glossary_id else None,
                metadata={
                    'provider': 'openmetadata',
                    'fqn': entity.get('fullyQualifiedName'),
                    'tags': tags,
                    'extension': extension,
                    'fetched_at': datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.error(f"Error parsing OpenMetadata term entity: {e}")
            return None
