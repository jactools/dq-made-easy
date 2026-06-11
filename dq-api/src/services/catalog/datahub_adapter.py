"""
DataHub Catalog Adapter

Implementation of CatalogAdapter for integration with DataHub
(https://datahubproject.io/)
"""

import aiohttp
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from .adapter import CatalogAdapter, CatalogConfig, BusinessTerm

logger = logging.getLogger(__name__)


class DataHubCatalogAdapter(CatalogAdapter):
    """DataHub-specific catalog adapter using GraphQL API"""
    
    def __init__(self, config: CatalogConfig):
        if config.provider != 'datahub':
            raise ValueError(f"DataHubCatalogAdapter requires provider='datahub', got '{config.provider}'")
        super().__init__(config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.graphql_endpoint = f"{config.endpoint}/api/graphql"
    
    async def connect(self) -> None:
        """Establish HTTP session to DataHub"""
        try:
            self.session = aiohttp.ClientSession(
                headers={
                    'Authorization': f'Bearer {self.config.api_key}',
                    'Content-Type': 'application/json',
                }
            )
            await self.is_healthy()
            self.connected = True
            logger.info(f"Connected to DataHub at {self.config.endpoint}")
        except Exception as e:
            logger.error(f"Failed to connect to DataHub: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.connected = False
            logger.info("Disconnected from DataHub")
    
    async def is_healthy(self) -> bool:
        """Check DataHub health via health endpoint"""
        if not self.session:
            return False
        
        try:
            health_endpoint = f"{self.config.endpoint}/health"
            async with self.session.get(health_endpoint, timeout=self.config.timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('status') == 'ok'
                return False
        except Exception as e:
            logger.warning(f"DataHub health check failed: {e}")
            return False
    
    async def fetch_all_terms(self) -> List[BusinessTerm]:
        """
        Fetch all Data Quality Dimensions from DataHub via GraphQL
        
        Paginated query to handle large term sets.
        """
        terms = []
        start = 0
        has_more = True
        
        while has_more:
            query = """
            query {
              search(input: {
                type: "DATASET"
                query: "tag:data_quality_dimension"
                start: %d
                count: %d
              }) {
                entities {
                  urn
                  entity {
                    ... on DatasetSnapshot {
                      dataset {
                        platformName
                        name
                        properties {
                          description
                          tags
                          customProperties {
                            key
                            value
                          }
                        }
                      }
                    }
                  }
                }
                pageSize
                total
              }
            }
            """ % (start, self.config.batch_size)
            
            try:
                entities = await self._execute_graphql(query)
                if entities:
                    for entity in entities:
                        term = self._parse_entity_to_term(entity)
                        if term:
                            terms.append(term)
                    
                    # Check if more results available
                    has_more = len(entities) == self.config.batch_size
                    start += self.config.batch_size
                else:
                    has_more = False
            except Exception as e:
                logger.error(f"Error fetching terms batch at offset {start}: {e}")
                raise
        
        logger.info(f"Fetched {len(terms)} terms from DataHub")
        return terms
    
    async def fetch_terms_by_domain(self, domain: str) -> List[BusinessTerm]:
        """Fetch terms filtered by domain/glossary"""
        query = """
        query {
          search(input: {
            type: "DATASET"
            query: "tag:data_quality_dimension domain:%s"
            start: 0
            count: %d
          }) {
            entities {
              urn
              entity {
                ... on DatasetSnapshot { dataset { platformName name properties {
                  description tags customProperties { key value }
                }}}
              }
            }
          }
        }
        """ % (domain, self.config.batch_size)
        
        try:
            entities = await self._execute_graphql(query)
            return [
                self._parse_entity_to_term(e) 
                for e in entities 
                if self._parse_entity_to_term(e)
            ]
        except Exception as e:
            logger.error(f"Error fetching terms for domain {domain}: {e}")
            return []
    
    async def search_terms(self, query_str: str) -> List[BusinessTerm]:
        """Search terms by name or keyword"""
        query = """
        query {
          search(input: {
            type: "DATASET"
            query: "tag:data_quality_dimension %s"
            start: 0
            count: %d
          }) {
            entities {
              urn
              entity {
                ... on DatasetSnapshot { dataset { platformName name properties {
                  description tags customProperties { key value }
                }}}
              }
            }
          }
        }
        """ % (query_str, self.config.batch_size)
        
        try:
            entities = await self._execute_graphql(query)
            return [
                self._parse_entity_to_term(e) 
                for e in entities 
                if self._parse_entity_to_term(e)
            ]
        except Exception as e:
            logger.error(f"Error searching terms for '{query_str}': {e}")
            return []
    
    async def get_term_details(self, term_key: str) -> Optional[BusinessTerm]:
        """Get detailed information for a specific term"""
        query = """
        query {
          dataset(urn: "%s") {
            urn
            name
            platformName
            properties {
              description
              tags
              customProperties {
                key
                value
              }
            }
          }
        }
        """ % term_key
        
        try:
            data = await self._execute_graphql(query)
            if data:
                return self._parse_entity_to_term({'urn': term_key, 'dataset': data})
            return None
        except Exception as e:
            logger.error(f"Error fetching term details for {term_key}: {e}")
            return None
    
    async def _execute_graphql(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Execute GraphQL query against DataHub"""
        if not self.session:
            raise RuntimeError("Not connected to DataHub")
        
        try:
            async with self.session.post(
                self.graphql_endpoint,
                json={'query': query},
                timeout=self.config.timeout
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if 'errors' in result:
                        logger.warning(f"GraphQL errors: {result['errors']}")
                        return None
                    return result.get('data', {}).get('search', {}).get('entities', [])
                else:
                    logger.error(f"DataHub API error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"GraphQL query failed: {e}")
            raise
    
    def _parse_entity_to_term(self, entity: Dict[str, Any]) -> Optional[BusinessTerm]:
        """Convert DataHub entity to BusinessTerm"""
        try:
            urn = entity.get('urn', '')
            dataset = entity.get('entity', {}).get('dataset', {})
            
            if not dataset:
                return None
            
            props = dataset.get('properties', {})
            custom_props = {p['key']: p['value'] for p in props.get('customProperties', [])}
            
            return BusinessTerm(
                term_key=urn,
                term_name=dataset.get('name', ''),
                description=props.get('description'),
                data_type=custom_props.get('dataType'),
                domain=custom_props.get('domain'),
                glossary_id=custom_props.get('glossaryId'),
                metadata={
                    'platform': dataset.get('platformName'),
                    'tags': props.get('tags', []),
                    'custom_properties': custom_props,
                    'fetched_at': datetime.utcnow().isoformat(),
                }
            )
        except Exception as e:
            logger.error(f"Error parsing entity to term: {e}")
            return None
