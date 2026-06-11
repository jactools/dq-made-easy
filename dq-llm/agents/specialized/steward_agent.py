"""
Data Steward Agent for DQ-RuleBuilder Pi Agent Harness.

This specialized agent assists with data definition and governance.

Purpose:
    Help data stewards generate definitions, manage glossary entries, and ensure
    data governance compliance across the DQ-RuleBuilder platform.

Capabilities:
    - Generate data definitions from context
    - Create and update glossary entries
    - Suggest data stewards and ownership
    - Validate definitions against policies
    - Track approval workflows
    - Align with BCBS 239 principles

Related Work:
    - dq-llm/entrypoint.py: Existing generate_data_definitions endpoint
    - BCBS 239: Principles for Effective Risk Data Aggregation and Risk Reporting

Tracked Work Item: LLM-1.9
Milestone: C (Full Agent Suite)
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# Try to import Pi Agent classes, with graceful fallback for development
try:
    from pi_agent import Agent as PiAgent
    from pi_agent import Tool as PiTool
    PI_AGENT_AVAILABLE = True
except ImportError:
    PI_AGENT_AVAILABLE = False

from ..base import DQAgent, DQAgentError, AgentStatus
from ..config import DQAgentConfig, get_agent_config
from ..tools.definition_tools import DefinitionTool

logger = logging.getLogger(__name__)


# BCBS 239 principles for reference
BCBS_239_PRINCIPLES = {
    "principle_1": {
        "name": "Governance",
        "description": "Strong governance framework for risk data and reporting",
        "key_aspects": [
            "Clear accountability and ownership",
            "Independent validation and controls",
            "Documented policies and procedures",
        ],
    },
    "principle_2": {
        "name": "Data Architecture and Infrastructure",
        "description": "Robust data architecture and IT infrastructure",
        "key_aspects": [
            "Integrated data architecture",
            "Accuracy and integrity of data",
            "Data dictionaries and metadata",
        ],
    },
    "principle_3": {
        "name": "Accuracy and Integrity",
        "description": "Accuracy and integrity of risk data",
        "key_aspects": [
            "Data quality validation",
            "Reconciliation processes",
            "Error correction and tracking",
        ],
    },
    "principle_4": {
        "name": "Complete",
        "description": "Completeness of risk data",
        "key_aspects": [
            "No missing material data",
            "All required data elements",
            "Historical data retention",
        ],
    },
    "principle_5": {
        "name": "Timely",
        "description": "Timeliness and punctuality of risk data",
        "key_aspects": [
            "Data available when needed",
            "Meet reporting deadlines",
            "Frequency of data updates",
        ],
    },
    "principle_6": {
        "name": "Adaptable",
        "description": "Adaptability of risk data and reporting",
        "key_aspects": [
            "Flexibility to meet new requirements",
            "Scalability for increased data volumes",
            "Respond to changing business needs",
        ],
    },
    "principle_7": {
        "name": "Aggregation Capabilities",
        "description": "Aggregation capabilities and risk reporting practices",
        "key_aspects": [
            "Granular to aggregated views",
            "Multiple aggregation levels",
            "Drill-down capabilities",
        ],
    },
    "principle_8": {
        "name": "Reporting",
        "description": "Risk data reporting practices",
        "key_aspects": [
            "Clear and accurate reports",
            "Consistent reporting formats",
            "Auditability and traceability",
        ],
    },
    "principle_9": {
        "name": "Communication",
        "description": "Communication of information",
        "key_aspects": [
            "Clear communication channels",
            "Stakeholder engagement",
            "Documentation and training",
        ],
    },
    "principle_10": {
        "name": "Supervisory Review",
        "description": "Supervisory review and validation",
        "key_aspects": [
            "Independent review processes",
            "Validation of data accuracy",
            "Remediation of issues",
        ],
    },
    "principle_11": {
        "name": "Tools and Technology",
        "description": "Use of tools and technology",
        "key_aspects": [
            "Appropriate tools for data management",
            "Automation of data processes",
            "Integration with existing systems",
        ],
    },
}

# Definition status levels
class DefinitionStatus(str):
    """Definition lifecycle status."""
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


# Definition quality criteria
DEFINITION_QUALITY_CRITERIA = [
    "Starts with 'A' or 'An' (for business definitions)",
    "Expresses the essence of the term",
    "Avoids circular wording (e.g., 'a customer is someone who is a customer')",
    "Avoids embedded business rules",
    "Avoids purpose/function language ('used for', 'used to')",
    "Unambiguous and aligns with logical data model",
    "Value-domain expectations, constraints, and examples are explicit",
    "Identifies accountable stewardship and source provenance",
    "Traceable and governable for audit needs",
]


class DataStewardAgent(DQAgent):
    """
    Specialized agent for data definition and governance.
    
    This agent helps data stewards:
    1. Generate data definitions from context
    2. Create and update glossary entries
    3. Suggest data stewards and ownership
    4. Validate definitions against policies (BCBS 239)
    5. Track approval workflows
    6. Ensure traceability and auditability
    
    The agent integrates with the existing dq-llm generate_data_definitions
    endpoint and OpenMetadata for glossary management.
    
    Attributes:
        definition_tool: The DefinitionTool instance
        generated_definitions: Definitions generated in current session
        glossary_entries: Glossary entries created/updated
        approval_workflows: Tracked approval workflows
    """
    
    # System prompt from feature specification (Phase 3.3)
    SYSTEM_PROMPT = """
    You are a Data Steward for DQ-RuleBuilder.
    Your expertise: data definitions, glossary management, data governance.
    
    Primary Tasks:
    1. Generate data definitions from context
    2. Create and update glossary entries
    3. Suggest data stewards and ownership
    4. Validate definitions against policies
    5. Track approval workflows
    
    Guidelines:
    - Ensure definitions align with business meaning
    - Identify accountable stewardship
    - Source provenance for all definitions
    - Validate against BCBS 239 principles
    - Maintain traceability for audit needs
    - Use ISO 11179 standards for metadata
    - Follow organization's data governance framework
    
    Definition Quality Criteria (Guidelines for Definitions of Business Terms v1.0):
    - Business definition must start with 'A' or 'An'
    - Express the essence of the term
    - Avoid circular wording
    - Avoid embedded business rules
    - Avoid purpose/function language such as 'used for'
    - Value-domain expectations, constraints, and examples are explicit and reviewable
    - The definition identifies accountable stewardship and source provenance
    - The definition is traceable and governable for BCBS 239 evidence and audit needs
    
    BCBS 239 Alignment:
    Consider the following BCBS 239 principles when creating definitions:
    - Governance: Clear accountability and ownership
    - Accuracy and Integrity: Data quality validation and reconciliation
    - Complete: No missing material data elements
    - Timely: Data available when needed
    - Adaptable: Flexibility to meet new requirements
    - Aggregation: Granular to aggregated views
    - Reporting: Clear and accurate reports
    - Communication: Clear communication channels
    - Supervisory Review: Independent review processes
    - Tools and Technology: Appropriate tools for data management
    
    Response Format:
    - Use clear, business-friendly language
    - Include source references and provenance
    - Identify stewardship and ownership
    - Note BCBS 239 alignment where applicable
    - Use markdown for structure and readability
    
    Best Practices:
    - Align definitions with existing glossaries
    - Cross-reference related terms
    - Include synonyms and abbreviations
    - Document constraints and allowed values
    - Provide examples for clarity
    - Link to source systems and reference data
    """
    
    def __init__(
        self,
        name: str = "dq_steward_agent",
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[DQAgentConfig] = None,
        session_id: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize the Data Steward Agent.
        
        Args:
            name: Agent name
            api_base_url: Base URL for DQ-API (overrides config)
            api_key: API key for authentication (overrides config)
            config: DQAgentConfig instance
            session_id: Session identifier
            **kwargs: Additional arguments passed to DQAgent
        """
        # Get configuration
        self.agent_config = config or get_agent_config()
        
        # Use provided API config or fall back to global config
        effective_api_base_url = api_base_url or self.agent_config.api_base_url
        effective_api_key_provider = self.agent_config.get_api_key_provider(api_key)
        
        # Initialize definition tool
        self.definition_tool = DefinitionTool(
            api_base_url=effective_api_base_url,
            api_key_provider=effective_api_key_provider
        )
        
        # Track stewardship state
        self.generated_definitions: List[Dict[str, Any]] = []
        self.glossary_entries: Dict[str, Dict[str, Any]] = {}
        self.approval_workflows: Dict[str, Dict[str, Any]] = {}
        self.current_definition_id: Optional[str] = None
        self.current_glossary_name: Optional[str] = None
        self.steward_suggestions: Dict[str, Any] = {}
        
        # Initialize parent with definition tool
        super().__init__(
            name=name,
            session_id=session_id,
            config=self.agent_config,
            tools=[self.definition_tool],
            system_prompt=self.SYSTEM_PROMPT,
            **kwargs
        )
        
        logger.info(f"DataStewardAgent '{name}' initialized with session {self.session_id}")
    
    async def generate_definition(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Generate data definitions from context.
        
        This method calls the dq-llm generate_data_definitions endpoint
        and processes the results for steward review.
        
        Args:
            request: Definition generation request (matches DataDefinitionRequest)
            context: Additional context for generation
            **kwargs: Additional parameters
            
        Returns:
            Generated definitions with steward review information
        """
        self.generated_definitions = []
        
        try:
            # Call the definition tool to generate definitions
            result = await self.definition_tool.generate(request)
            
            if isinstance(result, dict):
                definitions = result.get("definitions", [])
                if isinstance(definitions, list):
                    self.generated_definitions = definitions
            
            # Process the results for steward review
            processed_result = self._process_generation_result(result, request)
            
            return {
                **processed_result,
                "success": True,
                "definitions_generated": len(self.generated_definitions),
            }
            
        except Exception as e:
            logger.error(f"Definition generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "definitions": [],
            }
    
    async def create_glossary_entry(
        self,
        entry: Dict[str, Any],
        glossary_name: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Create a glossary entry.
        
        Args:
            entry: Glossary entry configuration
            glossary_name: Name of the glossary to add to
            **kwargs: Additional parameters
            
        Returns:
            Created glossary entry with ID
        """
        try:
            # Normalize the entry
            normalized_entry = self._normalize_glossary_entry(entry)
            
            # Set glossary name
            if glossary_name:
                normalized_entry["glossary"] = glossary_name
                self.current_glossary_name = glossary_name
            elif "glossary" not in normalized_entry:
                # Default glossary name
                normalized_entry["glossary"] = "default"
                self.current_glossary_name = "default"
            else:
                self.current_glossary_name = normalized_entry["glossary"]
            
            # Generate entry ID
            entry_id = self._generate_entry_id(normalized_entry)
            normalized_entry["entry_id"] = entry_id
            self.current_definition_id = entry_id
            
            # Store the entry
            self.glossary_entries[entry_id] = normalized_entry
            
            # Note: This would call the actual glossary API in production
            # For now, return the normalized entry
            return {
                "success": True,
                "entry_id": entry_id,
                "glossary_name": normalized_entry["glossary"],
                "entry": normalized_entry,
                "message": f"Glossary entry '{normalized_entry.get('term')}' created",
            }
            
        except Exception as e:
            logger.error(f"Glossary entry creation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "entry": entry,
            }
    
    async def update_glossary_entry(
        self,
        entry_id: str,
        updates: Dict[str, Any],
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Update an existing glossary entry.
        
        Args:
            entry_id: ID of the entry to update
            updates: Dictionary of updates to apply
            **kwargs: Additional parameters
            
        Returns:
            Updated glossary entry
        """
        try:
            if entry_id not in self.glossary_entries:
                return {
                    "success": False,
                    "error": f"Entry {entry_id} not found",
                    "entry_id": entry_id,
                }
            
            # Get existing entry
            existing_entry = self.glossary_entries[entry_id]
            
            # Apply updates
            updated_entry = {**existing_entry, **updates}
            
            # Re-normalize
            normalized_entry = self._normalize_glossary_entry(updated_entry)
            
            # Update storage
            self.glossary_entries[entry_id] = normalized_entry
            
            return {
                "success": True,
                "entry_id": entry_id,
                "entry": normalized_entry,
                "message": f"Glossary entry {entry_id} updated",
            }
            
        except Exception as e:
            logger.error(f"Glossary entry update failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "entry_id": entry_id,
            }
    
    async def query_metadata(
        self,
        query: Dict[str, Any],
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Query the metadata catalog.
        
        Args:
            query: Metadata query parameters
            **kwargs: Additional parameters
            
        Returns:
            Query results with metadata information
        """
        try:
            result = await self.definition_tool.query_metadata(query)
            return result
        except Exception as e:
            logger.error(f"Metadata query failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": [],
            }
    
    async def search_definitions(
        self,
        query: str,
        glossary_name: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Search existing data definitions.
        
        Args:
            query: Search query string
            glossary_name: Optional glossary name to search within
            **kwargs: Additional search parameters
            
        Returns:
            Search results with matching definitions
        """
        try:
            # Search through generated definitions and glossary entries
            results = []
            
            query_lower = query.lower()
            
            # Search generated definitions
            for defn in self.generated_definitions:
                if self._matches_search(defn, query_lower):
                    results.append({
                        "source": "generated",
                        "match_score": self._calculate_match_score(defn, query_lower),
                        **defn
                    })
            
            # Search glossary entries
            for entry_id, entry in self.glossary_entries.items():
                if self._matches_search(entry, query_lower):
                    results.append({
                        "source": "glossary",
                        "entry_id": entry_id,
                        "match_score": self._calculate_match_score(entry, query_lower),
                        **entry
                    })
            
            # Sort by match score
            results.sort(key=lambda x: x.get("match_score", 0), reverse=True)
            
            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
            }
            
        except Exception as e:
            logger.error(f"Definition search failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": [],
            }
    
    async def validate_definition(
        self,
        definition: Dict[str, Any],
        against_policies: Optional[List[str]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Validate a definition against governance policies.
        
        Args:
            definition: Definition to validate
            against_policies: Specific policies to validate against
            **kwargs: Additional validation parameters
            
        Returns:
            Validation result with compliance status and issues
        """
        try:
            issues = []
            warnings = []
            recommendations = []
            
            # Validate against definition quality criteria
            quality_score, quality_issues = self._validate_quality(definition)
            issues.extend(quality_issues)
            
            # Validate BCBS 239 alignment
            bcbs_score, bcbs_issues = self._validate_bcbs239(definition)
            if bcbs_score < 100:
                warnings.extend(bcbs_issues)
            
            # Validate against specific policies if provided
            if against_policies:
                policy_issues = self._validate_against_policies(definition, against_policies)
                issues.extend(policy_issues)
            
            # Determine compliance status
            if not issues:
                compliance_status = "COMPLIANT"
            elif len(issues) <= 2 and not any("ERROR" in str(i) for i in issues):
                compliance_status = "CONITIONAL"
            else:
                compliance_status = "NON_COMPLIANT"
            
            return {
                "success": True,
                "compliance_status": compliance_status,
                "quality_score": quality_score,
                "bcbs239_score": bcbs_score,
                "issues": issues,
                "warnings": warnings,
                "recommendations": recommendations,
            }
            
        except Exception as e:
            logger.error(f"Definition validation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "compliance_status": "VALIDATION_ERROR",
            }
    
    async def suggest_stewards(
        self,
        metadata: Dict[str, Any],
        domain: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Suggest data stewards and ownership based on metadata.
        
        Args:
            metadata: Metadata information (tables, domains, etc.)
            domain: Specific domain to focus on
            **kwargs: Additional parameters
            
        Returns:
            Steward suggestions with rationale
        """
        try:
            suggestions = {
                "domain_stewards": [],
                "table_stewards": [],
                "field_stewards": [],
                "recommendations": [],
            }
            
            # Analyze metadata for stewardship patterns
            self.steward_suggestions = self._analyze_stewardship(metadata, domain)
            
            # Suggest domain stewards
            if domain:
                domain_steward = self._suggest_domain_steward(domain, metadata)
                if domain_steward:
                    suggestions["domain_stewards"].append(domain_steward)
            else:
                # Suggest for all domains
                domains = self._extract_domains(metadata)
                for d in domains:
                    domain_steward = self._suggest_domain_steward(d, metadata)
                    if domain_steward:
                        suggestions["domain_stewards"].append(domain_steward)
            
            # Suggest table stewards
            tables = metadata.get("tables", [])
            for table in tables:
                table_steward = self._suggest_table_steward(table, metadata)
                if table_steward:
                    suggestions["table_stewards"].append(table_steward)
            
            # Add general recommendations
            if not suggestions["domain_stewards"]:
                suggestions["recommendations"].append(
                    "No domain stewardship information available. "
                    "Consider establishing domain-level data stewards."
                )
            
            return {
                **suggestions,
                "metadata_analyzed": {
                    "table_count": len(tables),
                    "domain_count": len(domains),
                },
            }
            
        except Exception as e:
            logger.error(f"Steward suggestion failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "suggestions": [],
            }
    
    async def create_approval_workflow(
        self,
        definition_id: str,
        board_name: str = "Data Definition Board",
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Create an approval workflow for a definition.
        
        Args:
            definition_id: ID of the definition to approve
            board_name: Name of the approval board
            **kwargs: Additional workflow parameters
            
        Returns:
            Workflow information with status tracking
        """
        try:
            workflow_id = f"workflow_{definition_id}_{int(datetime.utcnow().timestamp())}"
            
            workflow = {
                "workflow_id": workflow_id,
                "definition_id": definition_id,
                "board_name": board_name,
                "status": DefinitionStatus.DRAFT,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "steps": [
                    {
                        "step_id": "review_1",
                        "name": "Initial Review",
                        "status": "pending",
                        "assigned_to": None,
                        "comments": [],
                    },
                    {
                        "step_id": "steward_review",
                        "name": "Data Steward Review",
                        "status": "pending",
                        "assigned_to": None,
                        "comments": [],
                    },
                    {
                        "step_id": "board_review",
                        "name": "Board Review",
                        "status": "pending",
                        "assigned_to": None,
                        "comments": [],
                    },
                    {
                        "step_id": "approval",
                        "name": "Final Approval",
                        "status": "pending",
                        "assigned_to": None,
                        "comments": [],
                    },
                ],
                "feedback": [],
                "approval_history": [],
            }
            
            self.approval_workflows[workflow_id] = workflow
            
            return {
                "success": True,
                "workflow_id": workflow_id,
                "workflow": workflow,
                "message": f"Approval workflow created for definition {definition_id}",
            }
            
        except Exception as e:
            logger.error(f"Workflow creation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "definition_id": definition_id,
            }
    
    async def get_approval_status(
        self,
        workflow_id: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Get the current status of an approval workflow.
        
        Args:
            workflow_id: ID of the workflow
            **kwargs: Additional parameters
            
        Returns:
            Current workflow status
        """
        try:
            if workflow_id not in self.approval_workflows:
                return {
                    "success": False,
                    "error": f"Workflow {workflow_id} not found",
                    "workflow_id": workflow_id,
                }
            
            workflow = self.approval_workflows[workflow_id]
            
            # Calculate progress
            total_steps = len(workflow["steps"])
            completed_steps = sum(1 for s in workflow["steps"] if s["status"] == "completed")
            progress = (completed_steps / total_steps) * 100 if total_steps > 0 else 0
            
            return {
                "success": True,
                "workflow_id": workflow_id,
                "status": workflow["status"],
                "progress_percent": progress,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "steps": workflow["steps"],
                "current_step": self._get_current_step(workflow),
            }
            
        except Exception as e:
            logger.error(f"Status retrieval failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "workflow_id": workflow_id,
            }
    
    # ==================== Internal Methods ====================
    
    def _process_generation_result(
        self,
        result: Dict[str, Any],
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process definition generation result for steward review."""
        processed = {
            "definitions": [],
            "review_status": "pending",
            "open_questions": [],
            "board_notes": "",
            "approval_criteria": DEFINITION_QUALITY_CRITERIA.copy(),
        }
        
        if not result:
            return processed
        
        # Extract definitions from various possible locations
        definitions = result.get("definitions", [])
        if isinstance(definitions, list):
            for defn in definitions:
                if isinstance(defn, dict):
                    enriched_defn = self._enrich_definition(defn, request)
                    processed["definitions"].append(enriched_defn)
        
        # Extract review information
        processed["review_status"] = result.get("review_status", "pending")
        processed["board_review_summary"] = result.get("board_review_summary", "")
        processed["open_questions"] = result.get("open_questions", [])
        processed["board_notes"] = result.get("board_notes", "")
        
        # Validate each definition
        for i, defn in enumerate(processed["definitions"]):
            validation = self._validate_definition_structure(defn)
            if validation["issues"]:
                defn["_validation_issues"] = validation["issues"]
                defn["_validation_warnings"] = validation["warnings"]
        
        return processed
    
    def _enrich_definition(
        self,
        definition: Dict[str, Any],
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enrich a definition with steward-specific metadata."""
        enriched = definition.copy()
        
        # Add steward metadata
        enriched["_steward_metadata"] = {
            "reviewed": False,
            "reviewed_at": None,
            "reviewed_by": None,
            "quality_score": None,
            "bcbs239_alignment": {},
            "approval_status": DefinitionStatus.DRAFT,
            "last_updated": datetime.utcnow().isoformat(),
        }
        
        # Add provenance from request
        if request:
            enriched["_request_context"] = {
                "task_id": request.get("task_id"),
                "steward_name": request.get("steward_name"),
                "board_name": request.get("board_name"),
                "domain_name": request.get("domain_name"),
            }
        
        # Add BCBS 239 alignment suggestions
        enriched["_bcbs239_suggestions"] = self._suggest_bcbs239_alignment(enriched)
        
        return enriched
    
    def _validate_definition_structure(
        self,
        definition: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate a definition's structure."""
        issues = []
        warnings = []
        
        # Check required fields
        if not definition.get("definition_name"):
            issues.append("Missing definition_name")
        
        if not definition.get("business_definition"):
            issues.append("Missing business_definition")
        
        # Check business definition quality
        business_def = definition.get("business_definition", "")
        if business_def:
            quality_issues = self._validate_business_definition(business_def)
            warnings.extend(quality_issues)
        
        # Check for provenance
        if not definition.get("source_references"):
            warnings.append("No source references provided")
        
        if not definition.get("definition_owner"):
            warnings.append("No definition owner specified")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }
    
    def _validate_business_definition(self, business_def: str) -> List[str]:
        """Validate a business definition against quality criteria."""
        issues = []
        
        # Check if it starts with 'A' or 'An'
        stripped = business_def.strip()
        if not (stripped.startswith("A ") or stripped.startswith("An ")):
            issues.append(
                "Business definition should start with 'A' or 'An' "
                "(Guidelines for Definitions of Business Terms v1.0)"
            )
        
        # Check for circular wording (simplified check)
        definition_lower = stripped.lower()
        definition_words = stripped.split()
        if definition_words:
            first_word = definition_words[0].lower()
            if first_word in definition_lower[definition_lower.find(first_word) + len(first_word):]:
                # This is a very basic check - would need more sophisticated analysis
                pass  # Skip for now
        
        # Check for purpose/function language
        purpose_phrases = ["used for", "used to", "utilized for", "utilized to", "purpose is"]
        for phrase in purpose_phrases:
            if phrase in definition_lower:
                issues.append(
                    f"Business definition contains purpose/function language: '{phrase}' "
                    "(Guidelines for Definitions of Business Terms v1.0)"
                )
        
        return issues
    
    def _normalize_glossary_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a glossary entry to standard format."""
        normalized: Dict[str, Any] = {
            "term": entry.get("term") or entry.get("name") or entry.get("entry_name"),
            "display_name": entry.get("display_name") or entry.get("term") or entry.get("name"),
            "definition": entry.get("definition") or entry.get("business_definition") or entry.get("description"),
            "glossary": entry.get("glossary") or "default",
            "status": DefinitionStatus.DRAFT,
            "version": entry.get("version") or "1.0",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "created_by": entry.get("created_by") or entry.get("author"),
            "updated_by": entry.get("updated_by") or entry.get("author"),
            "synonyms": entry.get("synonyms") or entry.get("aliases") or [],
            "related_terms": entry.get("related_terms") or [],
            "categories": entry.get("categories") or [],
            "tags": entry.get("tags") or [],
            "source": entry.get("source") or entry.get("source_system"),
            "owner": entry.get("owner") or entry.get("definition_owner"),
            "steward": entry.get("steward") or entry.get("data_steward"),
            "metadata": entry.get("metadata") or {},
        }
        
        # Ensure term exists
        if not normalized["term"]:
            raise ValueError("Glossary entry must have a term or name")
        
        # Ensure definition exists
        if not normalized["definition"]:
            raise ValueError("Glossary entry must have a definition")
        
        return normalized
    
    def _generate_entry_id(self, entry: Dict[str, Any]) -> str:
        """Generate a unique ID for a glossary entry."""
        import hashlib
        
        term = entry.get("term") or ""
        glossary = entry.get("glossary") or "default"
        
        # Create a hash-based ID
        id_string = f"{glossary}:{term}"
        hash_obj = hashlib.md5(id_string.encode())
        hash_hex = hash_obj.hexdigest()[:8]
        
        # Clean term for ID
        term_clean = re.sub(r"[^a-zA-Z0-9]", "_", term).lower()
        
        return f"glossary_{glossary}_{term_clean}_{hash_hex}"
    
    def _matches_search(self, item: Dict[str, Any], query: str) -> bool:
        """Check if an item matches a search query."""
        # Search in various fields
        searchable_fields = [
            "term", "display_name", "definition", "business_definition",
            "description", "name", "definition_name"
        ]
        
        for field in searchable_fields:
            value = item.get(field)
            if value and query in str(value).lower():
                return True
        
        # Search in synonyms
        synonyms = item.get("synonyms") or item.get("aliases") or []
        for synonym in synonyms:
            if query in str(synonym).lower():
                return True
        
        return False
    
    def _calculate_match_score(self, item: Dict[str, Any], query: str) -> float:
        """Calculate a match score for search results."""
        score = 0.0
        
        # Check various fields
        searchable_fields = [
            ("term", 10.0),
            ("display_name", 10.0),
            ("definition", 5.0),
            ("business_definition", 5.0),
            ("description", 3.0),
        ]
        
        for field, weight in searchable_fields:
            value = item.get(field)
            if value and query in str(value).lower():
                score += weight
        
        # Check synonyms
        synonyms = item.get("synonyms") or item.get("aliases") or []
        for synonym in synonyms:
            if query in str(synonym).lower():
                score += 3.0
        
        # Check exact matches
        if query in (str(item.get("term")).lower(), str(item.get("display_name")).lower()):
            score += 5.0
        
        return score
    
    def _validate_quality(self, definition: Dict[str, Any]) -> tuple[float, List[str]]:
        """Validate a definition against quality criteria."""
        issues = []
        score = 100.0
        
        # Check required fields
        if not definition.get("definition_name"):
            issues.append("Missing definition_name")
            score -= 20
        
        if not definition.get("business_definition"):
            issues.append("Missing business_definition")
            score -= 20
        
        # Validate business definition
        business_def = definition.get("business_definition", "")
        def_issues = self._validate_business_definition(business_def)
        issues.extend(def_issues)
        score -= len(def_issues) * 5
        
        # Check provenance
        if not definition.get("source_references"):
            issues.append("No source references provided")
            score -= 10
        
        if not definition.get("definition_owner"):
            issues.append("No definition owner specified")
            score -= 10
        
        # Ensure score is within bounds
        score = max(0, min(100, score))
        
        return score, issues
    
    def _validate_bcbs239(self, definition: Dict[str, Any]) -> tuple[float, List[str]]:
        """Validate BCBS 239 alignment for a definition."""
        score = 100.0
        issues = []
        
        # Check for traceability
        if not definition.get("source_references"):
            issues.append("BCBS 239: Missing source references for traceability")
            score -= 15
        
        if not definition.get("provenance"):
            issues.append("BCBS 239: Missing provenance information")
            score -= 15
        
        # Check for governance
        if not definition.get("definition_owner"):
            issues.append("BCBS 239: Missing definition owner for governance")
            score -= 15
        
        if not definition.get("primary_domain"):
            issues.append("BCBS 239: Missing primary domain for governance alignment")
            score -= 10
        
        # Check for data quality
        if not definition.get("value_domain"):
            issues.append("BCBS 239: Missing value domain information for data quality")
            score -= 10
        
        # Ensure score is within bounds
        score = max(0, min(100, score))
        
        return score, issues
    
    def _validate_against_policies(
        self,
        definition: Dict[str, Any],
        policies: List[str]
    ) -> List[str]:
        """Validate a definition against specific policies."""
        issues = []
        
        # This would be customized based on organization's specific policies
        # For now, just check for common policy requirements
        
        for policy in policies:
            policy_lower = policy.lower()
            
            if "retention" in policy_lower:
                if not definition.get("retention_class"):
                    issues.append(f"Policy '{policy}': Missing retention class")
            
            if "classification" in policy_lower or "sensitivity" in policy_lower:
                if not definition.get("sensitivity"):
                    issues.append(f"Policy '{policy}': Missing sensitivity classification")
            
            if "lineage" in policy_lower:
                if not definition.get("lineage_refs"):
                    issues.append(f"Policy '{policy}': Missing lineage references")
        
        return issues
    
    def _suggest_bcbs239_alignment(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest BCBS 239 alignment for a definition."""
        suggestions = {
            "aligned_principles": [],
            "gap_analysis": [],
            "recommendations": [],
        }
        
        # Check for governance alignment
        if definition.get("definition_owner"):
            suggestions["aligned_principles"].append("Principle 1: Governance")
        else:
            suggestions["gap_analysis"].append(
                "Principle 1: Governance - Missing definition owner"
            )
            suggestions["recommendations"].append(
                "Identify and assign a definition owner for governance alignment"
            )
        
        # Check for data architecture alignment
        if definition.get("source_references"):
            suggestions["aligned_principles"].append("Principle 2: Data Architecture")
        else:
            suggestions["gap_analysis"].append(
                "Principle 2: Data Architecture - Missing source references"
            )
            suggestions["recommendations"].append(
                "Document source references for data architecture alignment"
            )
        
        # Check for accuracy and integrity alignment
        if definition.get("value_domain"):
            suggestions["aligned_principles"].append("Principle 3: Accuracy and Integrity")
        else:
            suggestions["gap_analysis"].append(
                "Principle 3: Accuracy and Integrity - Missing value domain"
            )
            suggestions["recommendations"].append(
                "Define value domain for accuracy and integrity validation"
            )
        
        # Check for completeness alignment
        if definition.get("constraints"):
            suggestions["aligned_principles"].append("Principle 4: Complete")
        
        # Check for traceability
        if definition.get("provenance"):
            suggestions["aligned_principles"].append("Principle 8: Reporting")
        else:
            suggestions["gap_analysis"].append(
                "Principle 8: Reporting - Missing provenance for traceability"
            )
        
        return suggestions
    
    def _analyze_stewardship(
        self,
        metadata: Dict[str, Any],
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze metadata for stewardship patterns."""
        analysis = {
            "domains": [],
            "domain_stewards": {},
            "table_stewards": {},
            "field_stewards": {},
        }
        
        # Extract domains
        domains = self._extract_domains(metadata)
        analysis["domains"] = domains
        
        # Analyze domain patterns
        for d in domains:
            analysis["domain_stewards"][d] = {
                "suggested_steward": self._suggest_domain_steward(d, metadata),
                "table_count": 0,
            }
        
        # Analyze table patterns
        tables = metadata.get("tables", [])
        for table in tables:
            table_name = table.get("name", "unknown")
            table_domain = table.get("domain") or domain or "unknown"
            
            if table_domain in analysis["domain_stewards"]:
                analysis["domain_stewards"][table_domain]["table_count"] += 1
            
            analysis["table_stewards"][table_name] = {
                "domain": table_domain,
                "suggested_steward": self._suggest_table_steward(table, metadata),
            }
        
        return analysis
    
    def _extract_domains(self, metadata: Dict[str, Any]) -> List[str]:
        """Extract domains from metadata."""
        domains = set()
        
        # Check for domains in metadata
        if "domains" in metadata:
            for domain in metadata["domains"]:
                if isinstance(domain, dict):
                    domains.add(domain.get("name") or domain.get("id", ""))
                else:
                    domains.add(str(domain))
        
        # Extract from tables
        tables = metadata.get("tables", [])
        for table in tables:
            domain = table.get("domain")
            if domain:
                domains.add(domain)
        
        return sorted(domains)
    
    def _suggest_domain_steward(self, domain: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest a steward for a domain."""
        # This would be customized based on organization's structure
        # For now, provide reasonable defaults
        
        domain_lower = domain.lower()
        
        # Map common domain patterns to likely stewards
        domain_stewards = {
            "finance": {
                "steward": "Finance Data Steward",
                "team": "Finance Team",
                "email": "finance-data-steward@company.com",
                "confidence": "high",
                "rationale": "Finance domains typically managed by Finance team",
            },
            "customer": {
                "steward": "Customer Data Steward",
                "team": "Customer Experience Team",
                "email": "customer-data-steward@company.com",
                "confidence": "high",
                "rationale": "Customer domains typically managed by Customer Experience team",
            },
            "product": {
                "steward": "Product Data Steward",
                "team": "Product Management Team",
                "email": "product-data-steward@company.com",
                "confidence": "high",
                "rationale": "Product domains typically managed by Product Management team",
            },
            "hr": {
                "steward": "HR Data Steward",
                "team": "Human Resources Team",
                "email": "hr-data-steward@company.com",
                "confidence": "high",
                "rationale": "HR domains typically managed by Human Resources team",
            },
            "risk": {
                "steward": "Risk Data Steward",
                "team": "Risk Management Team",
                "email": "risk-data-steward@company.com",
                "confidence": "high",
                "rationale": "Risk domains typically managed by Risk Management team",
            },
            "compliance": {
                "steward": "Compliance Data Steward",
                "team": "Compliance Team",
                "email": "compliance-data-steward@company.com",
                "confidence": "high",
                "rationale": "Compliance domains typically managed by Compliance team",
            },
        }
        
        # Check for exact match
        if domain_lower in domain_stewards:
            return domain_stewards[domain_lower]
        
        # Check for partial match
        for domain_pattern, steward_info in domain_stewards.items():
            if domain_pattern in domain_lower:
                return {**steward_info, "confidence": "medium"}
        
        # Default suggestion
        return {
            "steward": f"{domain} Data Steward",
            "team": f"{domain} Team",
            "email": f"{domain.lower()}-data-steward@company.com",
            "confidence": "low",
            "rationale": "Default suggestion based on domain name",
        }
    
    def _suggest_table_steward(self, table: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest a steward for a table."""
        # Default to domain steward
        domain = table.get("domain") or metadata.get("domain")
        if domain:
            domain_steward = self._suggest_domain_steward(domain, metadata)
            return {
                **domain_steward,
                "scope": "table",
                "table_name": table.get("name"),
                "rationale": f"Inherits from domain steward for '{domain}'",
            }
        
        # Fallback to table name pattern
        table_name = table.get("name", "unknown")
        table_lower = table_name.lower()
        
        # Map common table name patterns
        table_stewards = {
            "customer": {
                "steward": "Customer Data Steward",
                "team": "Customer Experience Team",
            },
            "account": {
                "steward": "Finance Data Steward",
                "team": "Finance Team",
            },
            "product": {
                "steward": "Product Data Steward",
                "team": "Product Management Team",
            },
            "employee": {
                "steward": "HR Data Steward",
                "team": "Human Resources Team",
            },
            "order": {
                "steward": "Sales Data Steward",
                "team": "Sales Team",
            },
        }
        
        for pattern, steward_info in table_stewards.items():
            if pattern in table_lower:
                return {
                    **steward_info,
                    "scope": "table",
                    "table_name": table_name,
                    "confidence": "medium",
                    "rationale": f"Suggested based on table name '{table_name}'",
                }
        
        # Default
        return {
            "steward": f"{table_name} Table Steward",
            "team": "Data Management Team",
            "scope": "table",
            "table_name": table_name,
            "confidence": "low",
            "rationale": "Default suggestion based on table name",
        }
    
    def _get_current_step(self, workflow: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the current step in a workflow."""
        for step in workflow.get("steps", []):
            if step.get("status") == "pending":
                return step
        return None
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current agent state including stewardship progress."""
        base_state = super().get_state()
        return {
            **base_state,
            "agent_type": "steward",
            "current_definition_id": self.current_definition_id,
            "current_glossary_name": self.current_glossary_name,
            "generated_definitions_count": len(self.generated_definitions),
            "glossary_entries_count": len(self.glossary_entries),
            "approval_workflows_count": len(self.approval_workflows),
        }
    
    def reset_state(self) -> None:
        """Reset the stewardship state."""
        self.generated_definitions.clear()
        self.glossary_entries.clear()
        self.approval_workflows.clear()
        self.current_definition_id = None
        self.current_glossary_name = None
        self.steward_suggestions = {}
        logger.info(f"DataStewardAgent {self.session_id}: State reset")
