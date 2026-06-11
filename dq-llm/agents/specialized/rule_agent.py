"""
Rule Engineer Agent for DQ-RuleBuilder Pi Agent Harness.

This specialized agent automates DQ rule creation and management (API-7).

Purpose:
    Automate data quality rule extraction, validation, assignment, and execution
    to help data stewards efficiently create and manage DQ rules.

Capabilities:
    - Extract rules from natural language requirements
    - Validate rule configurations against schema
    - Assign rules to specific metadata attributes
    - Execute rules and analyze results
    - Suggest rule improvements
    - Provide rule template suggestions

Related Work:
    - API-7: Real DQ Rule Execution
    - dq-llm/entrypoint.py: Existing extract_rules endpoint

Tracked Work Item: LLM-1.8
Milestone: C (Full Agent Suite)
"""

import logging
import re
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
from ..tools.rule_tools import RuleTool

logger = logging.getLogger(__name__)


# Rule type definitions for API-7
class RuleType(str):
    """Supported data quality rule types."""
    NOT_NULL = "NOT_NULL"              # Completeness check
    UNIQUE = "UNIQUE"                  # Uniqueness check
    PATTERN = "PATTERN"                # Format validity (regex)
    RANGE = "RANGE"                    # Value range validation
    IN_SET = "IN_SET"                  # Enumeration validation
    REFERENTIAL_INTEGRITY = "REFERENTIAL_INTEGRITY"  # Foreign key check
    CUSTOM_SQL = "CUSTOM_SQL"        # Custom SQL validation
    ACCURACY = "ACCURACY"              # Data accuracy check
    CONSISTENCY = "CONSISTENCY"        # Cross-field consistency


# Rule severity levels
class RuleSeverity(str):
    """Rule severity levels."""
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


# Rule category definitions
RULE_CATEGORIES = {
    RuleType.NOT_NULL: {
        "category": "Completeness",
        "description": "Ensures a field is not null/empty",
        "example": "email must not be null",
        "parameters": ["field_name"],
    },
    RuleType.UNIQUE: {
        "category": "Uniqueness",
        "description": "Ensures values are unique across the dataset",
        "example": "customer_id must be unique",
        "parameters": ["field_name"],
    },
    RuleType.PATTERN: {
        "category": "Validity",
        "description": "Validates field format against a regex pattern",
        "example": "email must match email pattern",
        "parameters": ["field_name", "pattern", "flags"],
    },
    RuleType.RANGE: {
        "category": "Validity",
        "description": "Validates numeric value is within a range",
        "example": "age must be between 0 and 120",
        "parameters": ["field_name", "min_value", "max_value"],
    },
    RuleType.IN_SET: {
        "category": "Validity",
        "description": "Validates value is in a set of allowed values",
        "example": "status must be one of: active, inactive, pending",
        "parameters": ["field_name", "allowed_values"],
    },
    RuleType.REFERENTIAL_INTEGRITY: {
        "category": "Consistency",
        "description": "Validates foreign key relationships",
        "example": "department_id must reference departments.id",
        "parameters": ["field_name", "reference_table", "reference_field"],
    },
    RuleType.CUSTOM_SQL: {
        "category": "Custom",
        "description": "Executes custom SQL validation logic",
        "example": "SELECT COUNT(*) FROM table WHERE condition",
        "parameters": ["sql_query", "expected_result"],
    },
    RuleType.ACCURACY: {
        "category": "Accuracy",
        "description": "Checks data accuracy against reference data",
        "example": "revenue must match source system",
        "parameters": ["field_name", "reference_source", "tolerance"],
    },
    RuleType.CONSISTENCY: {
        "category": "Consistency",
        "description": "Validates cross-field consistency rules",
        "example": "if status=active then end_date must be null",
        "parameters": ["condition", "expected_values"],
    },
}


class RuleEngineerAgent(DQAgent):
    """
    Specialized agent for data quality rule management.
    
    This agent helps data stewards:
    1. Extract rules from natural language requirements
    2. Validate rule configurations against schema
    3. Assign rules to metadata attributes
    4. Execute rules and analyze results
    5. Suggest rule improvements and best practices
    
    The agent integrates with API-7 (Real DQ Rule Execution) and the existing
    dq-llm extract_rules endpoint.
    
    Attributes:
        rule_tool: The RuleTool instance for API-7 operations
        extracted_rules: Rules extracted from current session
        validation_results: Results of rule validations
        execution_results: Results of rule executions
    """
    
    # System prompt from feature specification (Phase 3.2)
    SYSTEM_PROMPT = """
    You are a Data Quality Rule Engineer for DQ-RuleBuilder.
    Your expertise: data quality validation, business rule extraction, metadata assignment.
    
    Primary Tasks:
    1. Accept natural language requirements or structured specifications
    2. Extract potential DQ rules (completeness, uniqueness, validity, consistency, accuracy)
    3. Validate extracted rules against schema
    4. Assign rules to appropriate metadata attributes from connectors
    5. Execute rules and return results with explanations
    6. Iterate based on user feedback
    
    Rule Types to Consider:
    - NOT_NULL (completeness): Check that a field is not null
    - UNIQUE (uniqueness): Ensure values are unique
    - PATTERN (format validity): Validate against a regex pattern
    - RANGE (value range): Validate value is within a range
    - IN_SET (enumeration): Validate value is in a set of allowed values
    - REFERENTIAL_INTEGRITY (foreign key): Validate foreign key relationships
    - CUSTOM_SQL (custom validation): Execute custom SQL validation logic
    - ACCURACY (data accuracy): Check data accuracy against reference
    - CONSISTENCY (cross-field): Validate cross-field consistency rules
    
    Guidelines:
    - Always validate rules against available metadata
    - Provide clear explanations for extracted rules
    - Suggest appropriate rule types based on data characteristics
    - Ask for clarification on ambiguous requirements
    - Include severity levels (ERROR, WARNING, INFO) for rules
    - Consider performance implications of rule execution
    - Suggest indexing strategies for frequently validated fields
    
    Response Format:
    - Use markdown for rule definitions
    - Include code blocks for SQL patterns and custom logic
    - Provide examples for each rule type
    - Group related rules together (e.g., all rules for customers table)
    
    Best Practices:
    - Start with NOT_NULL and UNIQUE for primary keys
    - Add PATTERN validation for standardized fields (email, phone, etc.)
    - Use REFERENTIAL_INTEGRITY for foreign keys
    - Consider ACCURACY checks for critical business metrics
    - Use CONSISTENCY for business logic validation
    """
    
    def __init__(
        self,
        name: str = "dq_rule_agent",
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        config: Optional[DQAgentConfig] = None,
        session_id: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize the Rule Engineer Agent.
        
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
        
        # Initialize rule tool
        self.rule_tool = RuleTool(
            api_base_url=effective_api_base_url,
            api_key_provider=effective_api_key_provider
        )
        
        # Track rule engineering state
        self.extracted_rules: List[Dict[str, Any]] = []
        self.validation_results: Dict[str, Dict[str, Any]] = {}
        self.execution_results: Dict[str, Dict[str, Any]] = {}
        self.current_metadata_id: Optional[str] = None
        self.current_rule_id: Optional[str] = None
        
        # Initialize parent with rule tool
        super().__init__(
            name=name,
            session_id=session_id,
            config=self.agent_config,
            tools=[self.rule_tool],
            system_prompt=self.SYSTEM_PROMPT,
            **kwargs
        )
        
        logger.info(f"RuleEngineerAgent '{name}' initialized with session {self.session_id}")
    
    async def extract_rules(
        self,
        natural_language: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Extract data quality rules from natural language (API-7).
        
        This is the primary entry point for rule extraction. It:
        1. Analyzes the natural language input
        2. Identifies potential rule patterns
        3. Extracts structured rule configurations
        4. Validates against known rule types
        5. Returns structured rule definitions
        
        Args:
            natural_language: Natural language description of rules
            context: Optional context (metadata schema, table info, etc.)
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with:
            - success: bool
            - rules: List of extracted rule configurations
            - warnings: List of warnings or ambiguities
            - suggestions: List of suggested improvements
        """
        self.extracted_rules = []
        self.validation_results = {}
        
        try:
            # Call the rule tool to extract rules
            result = await self.rule_tool.extract(natural_language, context or {})
            
            if isinstance(result, list):
                raw_rules = result
            elif isinstance(result, dict):
                raw_rules = result.get("rules", result.get("data", []))
            else:
                raw_rules = []
            
            # Process extracted rules
            processed_rules = []
            warnings = []
            suggestions = []
            
            for rule in raw_rules:
                if isinstance(rule, dict):
                    processed_rule = self._normalize_rule(rule)
                    if processed_rule:
                        processed_rules.append(processed_rule)
                        
                        # Check for potential issues
                        rule_warnings, rule_suggestions = self._validate_rule_structure(processed_rule)
                        warnings.extend(rule_warnings)
                        suggestions.extend(rule_suggestions)
                else:
                    # Try to parse as string
                    parsed_rule = self._parse_rule_string(str(rule))
                    if parsed_rule:
                        processed_rules.append(parsed_rule)
            
            # If no rules were extracted, try enhanced extraction
            if not processed_rules:
                processed_rules = self._enhanced_extraction(natural_language, context)
            
            self.extracted_rules = processed_rules
            
            return {
                "success": True,
                "rules": processed_rules,
                "count": len(processed_rules),
                "warnings": warnings,
                "suggestions": suggestions,
                "context_used": context,
            }
            
        except Exception as e:
            logger.error(f"Rule extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "rules": [],
                "warnings": [],
                "suggestions": [],
            }
    
    async def create_rule(self, rule_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new data quality rule (API-7).
        
        Args:
            rule_config: Rule configuration dictionary
            
        Returns:
            Created rule with ID and status
        """
        try:
            # Normalize the rule configuration
            normalized_rule = self._normalize_rule(rule_config)
            if not normalized_rule:
                return {
                    "success": False,
                    "error": "Invalid rule configuration",
                    "rule_config": rule_config,
                }
            
            # Call the rule tool to create the rule
            result = await self.rule_tool.create(normalized_rule)
            
            if result.get("success", False) or result.get("rule_id"):
                rule_id = result.get("rule_id") or result.get("id")
                self.current_rule_id = rule_id
                self.extracted_rules.append({**normalized_rule, "rule_id": rule_id})
                return {
                    "success": True,
                    "rule_id": rule_id,
                    "rule": normalized_rule,
                    **result
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Rule creation failed"),
                    "rule_config": normalized_rule,
                    **result
                }
                
        except Exception as e:
            logger.error(f"Rule creation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "rule_config": rule_config,
            }
    
    async def validate_rule(self, rule_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a rule configuration against schema (API-7).
        
        Args:
            rule_config: Rule configuration to validate
            
        Returns:
            Validation result with errors and warnings
        """
        try:
            result = await self.rule_tool.validate(rule_config)
            rule_id = rule_config.get("rule_id") or self.current_rule_id
            
            if rule_id:
                self.validation_results[rule_id] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Rule validation failed: {e}", exc_info=True)
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": [],
            }
    
    async def assign_rule(
        self,
        rule_id: str,
        metadata_id: str,
        attribute_name: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Assign a rule to a metadata attribute (API-7).
        
        Args:
            rule_id: ID of the rule to assign
            metadata_id: ID of the metadata element
            attribute_name: Name of the attribute (optional)
            **kwargs: Additional assignment parameters
            
        Returns:
            Assignment result
        """
        self.current_rule_id = rule_id
        self.current_metadata_id = metadata_id
        
        try:
            # Build assignment payload
            threshold_override = kwargs.get("threshold_override")
            
            # Call the actual RuleTool.assign method
            result = await self.rule_tool.assign(
                rule_id=rule_id,
                metadata_id=metadata_id,
                threshold_override=threshold_override
            )
            
            logger.info(f"Rule {rule_id} assigned to metadata {metadata_id}")
            return result
            
        except Exception as e:
            logger.error(f"Rule assignment failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "rule_id": rule_id,
                "metadata_id": metadata_id,
            }
    
    async def execute_rule(
        self,
        rule_id: str,
        data: Optional[Dict[str, Any]] = None,
        metadata_id: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Execute a rule and return results (API-7).
        
        Args:
            rule_id: ID of the rule to execute
            data: Optional data to validate against
            metadata_id: Optional metadata ID for context
            **kwargs: Additional execution parameters
            
        Returns:
            Execution result with pass/fail status and details
        """
        self.current_rule_id = rule_id
        if metadata_id:
            self.current_metadata_id = metadata_id
        
        try:
            # Get data_object_version_id from kwargs or metadata context
            data_object_version_id = kwargs.get("data_object_version_id")
            
            # Call the actual RuleTool.execute method (API-7)
            result = await self.rule_tool.execute(
                rule_id=rule_id,
                data_object_version_id=data_object_version_id,
                data=data
            )
            
            logger.info(f"Rule {rule_id} executed successfully")
            
            # Store execution result
            self.execution_results[rule_id] = result
            return result
            
        except Exception as e:
            logger.error(f"Rule execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "rule_id": rule_id,
                "metadata_id": metadata_id,
            }
    
    async def analyze_rules(
        self,
        rules: List[Dict[str, Any]],
        metadata_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a set of rules and provide insights.
        
        Args:
            rules: List of rule configurations to analyze
            metadata_context: Optional metadata context for analysis
            
        Returns:
            Analysis with insights, recommendations, and potential issues
        """
        analysis = {
            "total_rules": len(rules),
            "by_type": {},
            "by_severity": {},
            "by_table": {},
            "coverage": {},
            "recommendations": [],
            "issues": [],
            "warnings": [],
        }
        
        # Categorize rules
        for rule in rules:
            rule_type = rule.get("rule_type", "UNKNOWN")
            severity = rule.get("severity", RuleSeverity.INFO)
            table = rule.get("table_name") or rule.get("metadata_id", "unknown")
            field = rule.get("field_name", "unknown")
            
            # Count by type
            analysis["by_type"][rule_type] = analysis["by_type"].get(rule_type, 0) + 1
            
            # Count by severity
            analysis["by_severity"][severity] = analysis["by_severity"].get(severity, 0) + 1
            
            # Count by table
            analysis["by_table"][table] = analysis["by_table"].get(table, 0) + 1
            
            # Track field coverage
            if table not in analysis["coverage"]:
                analysis["coverage"][table] = {"fields": set(), "rules": []}
            analysis["coverage"][table]["fields"].add(field)
            analysis["coverage"][table]["rules"].append(rule_type)
        
        # Generate recommendations
        if analysis["total_rules"] == 0:
            analysis["recommendations"].append(
                "No rules defined. Consider adding at least NOT_NULL rules for primary keys."
            )
        else:
            # Check for common patterns
            if "NOT_NULL" not in analysis["by_type"]:
                analysis["recommendations"].append(
                    "Consider adding NOT_NULL rules for critical fields that should never be null."
                )
            
            if "UNIQUE" not in analysis["by_type"]:
                analysis["recommendations"].append(
                    "Consider adding UNIQUE rules for primary key and unique constraint fields."
                )
            
            # Check for standard fields without PATTERN validation
            standard_pattern_fields = ["email", "phone", "zip_code", "ssn", "date"]
            for rule in rules:
                field = rule.get("field_name", "").lower()
                if any(pattern in field for pattern in standard_pattern_fields):
                    if rule.get("rule_type") != "PATTERN":
                        analysis["recommendations"].append(
                            f"Field '{rule.get('field_name')}' might benefit from PATTERN validation."
                        )
            
            # Check severity distribution
            if analysis["by_severity"].get(RuleSeverity.ERROR, 0) == 0:
                analysis["recommendations"].append(
                    "Consider marking critical rules (e.g., primary key NOT_NULL) as ERROR severity."
                )
        
        # Generate warnings
        tables_with_rules = set(analysis["by_table"].keys())
        if metadata_context:
            available_tables = set(metadata_context.get("tables", []))
            uncovered_tables = available_tables - tables_with_rules
            if uncovered_tables:
                analysis["warnings"].append(
                    f"Tables without rules: {', '.join(sorted(uncovered_tables))}"
                )
        
        return analysis
    
    async def suggest_rules(
        self,
        metadata: Dict[str, Any],
        requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suggest data quality rules based on metadata.
        
        Args:
            metadata: Metadata information (tables, columns, data types)
            requirements: Optional business requirements
            
        Returns:
            Suggested rules for the metadata
        """
        suggestions = {
            "suggested_rules": [],
            "by_table": {},
            "rationale": {},
        }
        
        tables = metadata.get("tables", [])
        
        for table_info in tables:
            table_name = table_info.get("name", "unknown")
            columns = table_info.get("columns", [])
            table_rules = []
            
            for col_info in columns:
                col_name = col_info.get("name", "unknown")
                data_type = col_info.get("data_type", "").lower()
                is_nullable = col_info.get("nullable", True)
                is_pk = col_info.get("is_primary_key", False)
                is_unique = col_info.get("is_unique", False)
                
                col_rules = []
                
                # Rule 1: NOT_NULL for primary keys
                if is_pk and is_nullable:
                    col_rules.append({
                        "rule_type": RuleType.NOT_NULL,
                        "field_name": col_name,
                        "severity": RuleSeverity.ERROR,
                        "reason": "Primary keys should never be null",
                    })
                elif is_pk:
                    col_rules.append({
                        "rule_type": RuleType.NOT_NULL,
                        "field_name": col_name,
                        "severity": RuleSeverity.ERROR,
                        "reason": "Primary keys should never be null",
                    })
                
                # Rule 2: UNIQUE for primary keys and unique constraints
                if is_pk or is_unique:
                    col_rules.append({
                        "rule_type": RuleType.UNIQUE,
                        "field_name": col_name,
                        "severity": RuleSeverity.ERROR,
                        "reason": "Primary keys and unique fields must have unique values",
                    })
                
                # Rule 3: PATTERN for standard formats
                pattern_rules = self._get_pattern_suggestions(col_name, data_type)
                col_rules.extend(pattern_rules)
                
                # Rule 4: RANGE for numeric fields
                if any(dt in data_type for dt in ["integer", "bigint", "smallint", "decimal", "numeric", "float", "double"]):
                    col_rules.append({
                        "rule_type": RuleType.RANGE,
                        "field_name": col_name,
                        "severity": RuleSeverity.WARNING,
                        "reason": "Numeric fields may need range validation",
                        "suggested_min": 0,
                        "suggested_max": None,
                    })
                
                # Rule 5: IN_SET for status-like fields
                if any(name in col_name.lower() for name in ["status", "state", "type", "category"]):
                    col_rules.append({
                        "rule_type": RuleType.IN_SET,
                        "field_name": col_name,
                        "severity": RuleSeverity.WARNING,
                        "reason": "Status/state fields typically have a limited set of valid values",
                        "suggested_values": [],
                    })
                
                # Add non-null suggestions for non-nullable fields
                if not is_nullable:
                    col_rules.append({
                        "rule_type": RuleType.NOT_NULL,
                        "field_name": col_name,
                        "severity": RuleSeverity.WARNING,
                        "reason": "Field is defined as NOT NULL in schema",
                    })
                
                # Deduplicate rules for this column
                unique_rules = []
                seen_rule_types = set()
                for rule in col_rules:
                    rule_type = rule.get("rule_type")
                    if rule_type not in seen_rule_types:
                        seen_rule_types.add(rule_type)
                        unique_rules.append(rule)
                
                for rule in unique_rules:
                    rule["table_name"] = table_name
                    table_rules.append(rule)
            
            if table_rules:
                suggestions["suggested_rules"].extend(table_rules)
                suggestions["by_table"][table_name] = table_rules
        
        return suggestions
    
    # ==================== Internal Methods ====================
    
    def _normalize_rule(self, rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a rule configuration to standard format."""
        if not rule:
            return None
        
        normalized: Dict[str, Any] = {
            "rule_type": self._map_rule_type(rule.get("rule_type") or rule.get("type", "")),
            "field_name": rule.get("field_name") or rule.get("column") or rule.get("field"),
            "table_name": rule.get("table_name") or rule.get("table"),
            "severity": RuleSeverity.INFO,
            "description": rule.get("description") or rule.get("reason") or "",
            "enabled": rule.get("enabled", True),
        }
        
        # Map severity
        severity = rule.get("severity") or rule.get("level")
        if severity:
            severity_upper = severity.upper()
            if severity_upper in ["ERROR", "CRITICAL", "HIGH"]:
                normalized["severity"] = RuleSeverity.ERROR
            elif severity_upper in ["WARNING", "MEDIUM"]:
                normalized["severity"] = RuleSeverity.WARNING
            elif severity_upper in ["INFO", "LOW"]:
                normalized["severity"] = RuleSeverity.INFO
        
        # Extract parameters based on rule type
        rule_type = normalized["rule_type"]
        
        if rule_type == RuleType.NOT_NULL:
            # No additional parameters needed
            pass
            
        elif rule_type == RuleType.UNIQUE:
            # No additional parameters needed
            pass
            
        elif rule_type == RuleType.PATTERN:
            normalized["pattern"] = rule.get("pattern") or rule.get("regex") or rule.get("expression")
            normalized["flags"] = rule.get("flags") or rule.get("pattern_flags")
            
        elif rule_type == RuleType.RANGE:
            normalized["min_value"] = rule.get("min_value") or rule.get("min")
            normalized["max_value"] = rule.get("max_value") or rule.get("max")
            normalized["inclusive"] = rule.get("inclusive", True)
            
        elif rule_type == RuleType.IN_SET:
            normalized["allowed_values"] = rule.get("allowed_values") or rule.get("values") or rule.get("enum") or []
            
        elif rule_type == RuleType.REFERENTIAL_INTEGRITY:
            normalized["reference_table"] = rule.get("reference_table") or rule.get("ref_table")
            normalized["reference_field"] = rule.get("reference_field") or rule.get("ref_field")
            
        elif rule_type == RuleType.CUSTOM_SQL:
            normalized["sql_query"] = rule.get("sql_query") or rule.get("query") or rule.get("sql")
            normalized["expected_result"] = rule.get("expected_result") or rule.get("expected")
            
        elif rule_type == RuleType.ACCURACY:
            normalized["reference_source"] = rule.get("reference_source") or rule.get("source")
            normalized["tolerance"] = rule.get("tolerance") or rule.get("threshold") or 0
            
        elif rule_type == RuleType.CONSISTENCY:
            normalized["condition"] = rule.get("condition") or rule.get("when")
            normalized["expected_values"] = rule.get("expected_values") or rule.get("then")
        
        # Add metadata
        normalized["metadata"] = {
            "source": rule.get("source"),
            "author": rule.get("author"),
            "tags": rule.get("tags") or [],
        }
        
        return normalized
    
    def _map_rule_type(self, rule_type: str) -> RuleType:
        """Map various rule type representations to standard RuleType."""
        if not rule_type:
            return RuleType.NOT_NULL
        
        type_upper = rule_type.upper().replace(" ", "_").replace("-", "_")
        
        # Map common variations
        type_mapping = {
            "NOT_NULL": RuleType.NOT_NULL,
            "NOTNULL": RuleType.NOT_NULL,
            "REQUIRED": RuleType.NOT_NULL,
            "MANDATORY": RuleType.NOT_NULL,
            "UNIQUE": RuleType.UNIQUE,
            "DISTINCT": RuleType.UNIQUE,
            "PATTERN": RuleType.PATTERN,
            "REGEX": RuleType.PATTERN,
            "FORMAT": RuleType.PATTERN,
            "RANGE": RuleType.RANGE,
            "BETWEEN": RuleType.RANGE,
            "MIN_MAX": RuleType.RANGE,
            "IN_SET": RuleType.IN_SET,
            "ENUM": RuleType.IN_SET,
            "ONE_OF": RuleType.IN_SET,
            "REFERENTIAL_INTEGRITY": RuleType.REFERENTIAL_INTEGRITY,
            "FOREIGN_KEY": RuleType.REFERENTIAL_INTEGRITY,
            "FK": RuleType.REFERENTIAL_INTEGRITY,
            "CUSTOM_SQL": RuleType.CUSTOM_SQL,
            "SQL": RuleType.CUSTOM_SQL,
            "CUSTOM": RuleType.CUSTOM_SQL,
            "ACCURACY": RuleType.ACCURACY,
            "CORRECTNESS": RuleType.ACCURACY,
            "CONSISTENCY": RuleType.CONSISTENCY,
            "CONSISTENT": RuleType.CONSISTENCY,
        }
        
        return type_mapping.get(type_upper, RuleType.NOT_NULL)
    
    def _parse_rule_string(self, rule_string: str) -> Optional[Dict[str, Any]]:
        """Parse a rule from a string representation."""
        rule_string = rule_string.strip()
        if not rule_string:
            return None
        
        # Try to match common patterns
        patterns = [
            # "field must be NOT_NULL"
            (rf"^(['\"\w\s]+)\s+(must\s+be|should\s+be|is|are)\s+(\w+)\s*$", self._parse_simple_rule),
            # "NOT_NULL for field"
            (rf"^(\w+)\s+(for|on)\s+(['\"\w\s]+)\s*$", self._parse_simple_rule),
            # "field should match pattern X"
            (rf"^(['\"\w\s]+)\s+(should|must)\s+(match|fit)\s+(pattern|regex)?\s+(['\".+\"'])\s*$", self._parse_pattern_rule),
            # "field should be in [a, b, c]"
            (rf"^(['\"\w\s]+)\s+(should|must)\s+be\s+(in|one\s+of)\s+(\[.+\])\s*$", self._parse_in_set_rule),
            # "field should be between X and Y"
            (rf"^(['\"\w\s]+)\s+(should|must)\s+be\s+(between|from)\s+(\d+)\s+and\s+(\d+)\s*$", self._parse_range_rule),
        ]
        
        for pattern, parser in patterns:
            match = re.match(pattern, rule_string, re.IGNORECASE)
            if match:
                try:
                    return parser(match)
                except Exception:
                    continue
        
        # Default: treat as NOT_NULL rule
        return {
            "rule_type": RuleType.NOT_NULL,
            "field_name": rule_string,
            "severity": RuleSeverity.INFO,
        }
    
    def _parse_simple_rule(self, match) -> Dict[str, Any]:
        """Parse a simple rule like 'field must be NOT_NULL'."""
        # match.group(1) = field name
        # match.group(3) = rule type
        field_name = match.group(1).strip().strip("'\"")
        rule_type_str = match.group(3).upper()
        
        return {
            "rule_type": self._map_rule_type(rule_type_str),
            "field_name": field_name,
            "severity": RuleSeverity.INFO,
        }
    
    def _parse_pattern_rule(self, match) -> Dict[str, Any]:
        """Parse a pattern rule like 'email should match pattern ^\\S+@\\S+\\.\\S+$'."""
        field_name = match.group(1).strip().strip("'\"")
        pattern = match.group(4).strip().strip("'\"")
        
        return {
            "rule_type": RuleType.PATTERN,
            "field_name": field_name,
            "pattern": pattern,
            "severity": RuleSeverity.INFO,
        }
    
    def _parse_in_set_rule(self, match) -> Dict[str, Any]:
        """Parse an IN_SET rule like 'status should be in [active, inactive, pending]'."""
        import json
        
        field_name = match.group(1).strip().strip("'\"")
        values_str = match.group(4).strip()
        
        # Parse the values
        try:
            # Try to parse as JSON array
            allowed_values = json.loads(values_str)
        except json.JSONDecodeError:
            # Try to parse as comma-separated list
            values_str = values_str.strip("[]").strip()
            allowed_values = [v.strip().strip("'\"") for v in values_str.split(",") if v.strip()]
        
        return {
            "rule_type": RuleType.IN_SET,
            "field_name": field_name,
            "allowed_values": allowed_values,
            "severity": RuleSeverity.INFO,
        }
    
    def _parse_range_rule(self, match) -> Dict[str, Any]:
        """Parse a range rule like 'age should be between 0 and 120'."""
        field_name = match.group(1).strip().strip("'\"")
        min_value = int(match.group(4))
        max_value = int(match.group(5))
        
        return {
            "rule_type": RuleType.RANGE,
            "field_name": field_name,
            "min_value": min_value,
            "max_value": max_value,
            "inclusive": True,
            "severity": RuleSeverity.INFO,
        }
    
    def _enhanced_extraction(
        self,
        natural_language: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Enhanced rule extraction using pattern matching and heuristics.
        
        This method attempts to extract rules when the LLM extraction
        doesn't return usable results.
        """
        rules = []
        text = natural_language.lower()
        
        # Pattern 1: "must not be null" or "cannot be null"
        null_pattern = re.compile(
            r"(\w+)\s+(must|should|cannot|can't|must\s+not)\s+(be\s+)?null",
            re.IGNORECASE
        )
        for match in null_pattern.finditer(natural_language):
            field = match.group(1)
            rules.append({
                "rule_type": RuleType.NOT_NULL,
                "field_name": field,
                "severity": RuleSeverity.ERROR,
                "source": "pattern_matching",
            })
        
        # Pattern 2: "must be unique"
        unique_pattern = re.compile(
            r"(\w+)\s+(must|should)\s+be\s+unique",
            re.IGNORECASE
        )
        for match in unique_pattern.finditer(natural_language):
            field = match.group(1)
            rules.append({
                "rule_type": RuleType.UNIQUE,
                "field_name": field,
                "severity": RuleSeverity.ERROR,
                "source": "pattern_matching",
            })
        
        # Pattern 3: "must match pattern/format"
        pattern_pattern = re.compile(
            r"(\w+)\s+(must|should)\s+(match|fit|follow)\s+(?:pattern|format|regex)?\s*(?:of|the)?\s*(['\"].+?['\"])",
            re.IGNORECASE
        )
        for match in pattern_pattern.finditer(natural_language):
            field = match.group(1)
            pattern = match.group(4).strip("'\"")
            rules.append({
                "rule_type": RuleType.PATTERN,
                "field_name": field,
                "pattern": pattern,
                "severity": RuleSeverity.WARNING,
                "source": "pattern_matching",
            })
        
        # Pattern 4: "must be one of"
        one_of_pattern = re.compile(
            r"(\w+)\s+(must|should)\s+be\s+(?:one\s+of\s+|in\s+)?(?:the\s+)?(\[[^\]]+\]|\{[^\}]+\}|[^\s,]+(?:,[^\s,]+)*)",
            re.IGNORECASE
        )
        for match in one_of_pattern.finditer(natural_language):
            field = match.group(1)
            values_str = match.group(3).strip("[]{} ")
            values = [v.strip() for v in values_str.split(",") if v.strip()]
            if values:
                rules.append({
                    "rule_type": RuleType.IN_SET,
                    "field_name": field,
                    "allowed_values": values,
                    "severity": RuleSeverity.WARNING,
                    "source": "pattern_matching",
                })
        
        # Pattern 5: "must be between X and Y"
        between_pattern = re.compile(
            r"(\w+)\s+(must|should)\s+be\s+(?:between|from)\s+(\d+)\s+and\s+(\d+)",
            re.IGNORECASE
        )
        for match in between_pattern.finditer(natural_language):
            field = match.group(1)
            min_val = int(match.group(3))
            max_val = int(match.group(4))
            rules.append({
                "rule_type": RuleType.RANGE,
                "field_name": field,
                "min_value": min_val,
                "max_value": max_val,
                "inclusive": True,
                "severity": RuleSeverity.WARNING,
                "source": "pattern_matching",
            })
        
        # Remove duplicates
        unique_rules = []
        seen = set()
        for rule in rules:
            key = (rule["rule_type"], rule["field_name"])
            if key not in seen:
                seen.add(key)
                unique_rules.append(rule)
        
        return unique_rules
    
    def _validate_rule_structure(self, rule: Dict[str, Any]) -> tuple[List[str], List[str]]:
        """Validate a rule structure and return warnings and suggestions."""
        warnings = []
        suggestions = []
        
        rule_type = rule.get("rule_type")
        field_name = rule.get("field_name")
        
        # Check required fields
        if not field_name:
            warnings.append(f"Rule is missing field_name: {rule}")
        
        # Type-specific validations
        if rule_type == RuleType.PATTERN:
            pattern = rule.get("pattern")
            if not pattern:
                warnings.append(f"PATTERN rule for '{field_name}' is missing pattern")
            else:
                # Try to validate pattern
                try:
                    import re
                    re.compile(pattern)
                except Exception as e:
                    warnings.append(f"Invalid regex pattern for '{field_name}': {e}")
        
        elif rule_type == RuleType.RANGE:
            min_val = rule.get("min_value")
            max_val = rule.get("max_value")
            if min_val is None:
                warnings.append(f"RANGE rule for '{field_name}' is missing min_value")
            if max_val is None:
                warnings.append(f"RANGE rule for '{field_name}' is missing max_value")
            if min_val is not None and max_val is not None and min_val > max_val:
                warnings.append(f"RANGE rule for '{field_name}': min_value ({min_val}) > max_value ({max_val})")
        
        elif rule_type == RuleType.IN_SET:
            values = rule.get("allowed_values", [])
            if not values:
                warnings.append(f"IN_SET rule for '{field_name}' has no allowed values")
        
        elif rule_type == RuleType.REFERENTIAL_INTEGRITY:
            ref_table = rule.get("reference_table")
            ref_field = rule.get("reference_field")
            if not ref_table:
                warnings.append(f"REFERENTIAL_INTEGRITY rule for '{field_name}' is missing reference_table")
            if not ref_field:
                warnings.append(f"REFERENTIAL_INTEGRITY rule for '{field_name}' is missing reference_field")
        
        # Suggest severity based on rule type
        if rule.get("severity") == RuleSeverity.INFO:
            if rule_type in [RuleType.NOT_NULL, RuleType.UNIQUE]:
                suggestions.append(
                    f"Consider setting severity to ERROR for {rule_type} rule on '{field_name}'"
                )
        
        return warnings, suggestions
    
    def _get_pattern_suggestions(self, field_name: str, data_type: str) -> List[Dict[str, Any]]:
        """Get pattern suggestions for a field based on its name and data type."""
        suggestions = []
        field_lower = field_name.lower()
        
        # Email pattern
        if "email" in field_lower:
            suggestions.append({
                "rule_type": RuleType.PATTERN,
                "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                "reason": "Email field should match standard email format",
            })
        
        # Phone pattern
        if any(name in field_lower for name in ["phone", "mobile", "telephone"]):
            suggestions.append({
                "rule_type": RuleType.PATTERN,
                "pattern": r"^\+?[\d\s\-\(\)]{10,15}$",
                "reason": "Phone field should match standard phone format",
            })
        
        # Date pattern (ISO 8601)
        if "date" in field_lower:
            suggestions.append({
                "rule_type": RuleType.PATTERN,
                "pattern": r"^\d{4}-\d{2}-\d{2}$",
                "reason": "Date field should match ISO 8601 format (YYYY-MM-DD)",
            })
        
        # UUID pattern
        if any(name in field_lower for name in ["uuid", "guid", "id"]) and "id" in field_lower:
            suggestions.append({
                "rule_type": RuleType.PATTERN,
                "pattern": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                "reason": "ID field should match UUID format",
            })
        
        # ZIP code pattern (US)
        if "zip" in field_lower or "postal" in field_lower:
            suggestions.append({
                "rule_type": RuleType.PATTERN,
                "pattern": r"^\d{5}(-\d{4})?$",
                "reason": "ZIP code should match US ZIP code format",
            })
        
        # SSN pattern
        if "ssn" in field_lower:
            suggestions.append({
                "rule_type": RuleType.PATTERN,
                "pattern": r"^\d{3}-\d{2}-\d{4}$",
                "reason": "SSN should match standard format (XXX-XX-XXXX)",
            })
        
        return suggestions
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current agent state including rule engineering progress."""
        base_state = super().get_state()
        return {
            **base_state,
            "agent_type": "rule",
            "current_rule_id": self.current_rule_id,
            "current_metadata_id": self.current_metadata_id,
            "extracted_rules_count": len(self.extracted_rules),
            "validation_results_count": len(self.validation_results),
            "execution_results_count": len(self.execution_results),
        }
    
    def reset_state(self) -> None:
        """Reset the rule engineering state."""
        self.extracted_rules.clear()
        self.validation_results.clear()
        self.execution_results.clear()
        self.current_metadata_id = None
        self.current_rule_id = None
        logger.info(f"RuleEngineerAgent {self.session_id}: State reset")
