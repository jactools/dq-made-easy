"""
Drift Detection Service for Business Terms & Aliases

Detects when catalog term definitions change and identifies affected rules.
Compares resolved aliases from previous rule versions with current catalog state.

Drift Types:
  - DATA_TYPE_CHANGED: Term's datatype was modified
  - DOMAIN_CHANGED: Term's domain/category was modified
  - TERM_DEPRECATED: Term was marked as deprecated/archived
  - TERM_RENAMED: Term was renamed
  - DEFINITION_CHANGED: Term's definition was modified
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from dq_api.src.models.models import (
    BusinessTerm,
    AliasSourceMetadata,
    RuleVersion,
    Rule,
)


class DriftType(str, Enum):
    """Types of drift detected"""
    DATA_TYPE_CHANGED = "data_type_changed"
    DOMAIN_CHANGED = "domain_changed"
    TERM_DEPRECATED = "term_deprecated"
    TERM_RENAMED = "term_renamed"
    DEFINITION_CHANGED = "definition_changed"


@dataclass
class TermDrift:
    """Single drift detected for a term"""
    drift_type: DriftType
    alias_name: str
    resolved_term_id: str
    resolved_term_name: str
    previous_value: str
    current_value: str
    change_detected_at: datetime
    severity: str  # 'critical' | 'warning' | 'info'


@dataclass
class RuleDrift:
    """Drift detected for a rule version"""
    rule_id: str
    rule_name: str
    rule_version_id: str
    version_number: int
    affected_aliases: List[str]
    drifts: List[TermDrift]
    total_drift_count: int
    needs_revalidation: bool
    last_validated_at: Optional[datetime]
    drift_detected_at: datetime


@dataclass
class DriftSummary:
    """Overall drift detection summary"""
    total_rules_checked: int
    rules_with_drift: int
    total_drifts_detected: int
    critical_drifts: int
    warning_drifts: int
    by_drift_type: Dict[str, int]
    affected_rules: List[RuleDrift]


class DriftDetectionService:
    """Service for detecting and tracking catalog term drift"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def detect_drift_for_rule(
        self,
        rule_id: str,
        rule_version_id: str,
    ) -> Optional[RuleDrift]:
        """
        Detect drift for a specific rule version.
        
        Compares resolved aliases from previous versions with current catalog state.
        
        Returns RuleDrift if drift detected, None otherwise.
        """
        # Get rule version with its alias mappings
        stmt = (
            select(RuleVersion)
            .where(
                (RuleVersion.id == rule_version_id) &
                (RuleVersion.rule_id == rule_id)
            )
        )
        rule_version = await self.session.scalar(stmt)
        if not rule_version:
            return None

        # Get rule
        stmt = select(Rule).where(Rule.id == rule_id)
        rule = await self.session.scalar(stmt)
        if not rule:
            return None

        # Get all alias mappings for this rule version
        stmt = (
            select(AliasSourceMetadata)
            .where(
                (AliasSourceMetadata.rule_version_id == rule_version_id) &
                (AliasSourceMetadata.is_current == True)
            )
        )
        result = await self.session.execute(stmt)
        alias_mappings = result.scalars().all()

        if not alias_mappings:
            return None

        # Check each alias for drift
        drifts: List[TermDrift] = []
        affected_aliases: set = set()

        for mapping in alias_mappings:
            drift = await self._check_term_drift(
                resolved_term_id=mapping.resolved_term_id,
                alias_name=mapping.alias_name,
                previous_term_name=mapping.resolved_term_name or "",
                previous_data_type=mapping.resolved_data_type or "unknown",
            )

            if drift:
                drifts.append(drift)
                affected_aliases.add(mapping.alias_name)

        if not drifts:
            return None

        # Determine severity
        critical_count = len([d for d in drifts if d.severity == 'critical'])
        needs_revalidation = critical_count > 0

        return RuleDrift(
            rule_id=rule_id,
            rule_name=rule.name,
            rule_version_id=rule_version_id,
            version_number=rule_version.version_number,
            affected_aliases=sorted(list(affected_aliases)),
            drifts=drifts,
            total_drift_count=len(drifts),
            needs_revalidation=needs_revalidation,
            last_validated_at=rule_version.created_at,
            drift_detected_at=datetime.utcnow(),
        )

    async def detect_drift_for_term(
        self,
        term_id: str,
    ) -> Optional[TermDrift]:
        """
        Detect if a specific term has drifted.
        
        Checks if term definition changed compared to last sync.
        
        Returns TermDrift if drift detected, None otherwise.
        """
        # Get current term
        stmt = select(BusinessTerm).where(BusinessTerm.id == term_id)
        current_term = await self.session.scalar(stmt)
        if not current_term:
            return None

        # Get previous mappings for this term
        stmt = (
            select(AliasSourceMetadata)
            .where(
                (AliasSourceMetadata.resolved_term_id == term_id) &
                (AliasSourceMetadata.is_current == True)
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        previous_mapping = result.scalars().first()

        if not previous_mapping:
            return None

        # Check for various drift types
        drifts: List[tuple] = []  # (drift_type, previous, current, severity)

        # Check datatype change
        if str(current_term.data_type or "").lower() != str(previous_mapping.resolved_data_type or "").lower():
            drifts.append((
                DriftType.DATA_TYPE_CHANGED,
                str(previous_mapping.resolved_data_type or "unknown"),
                str(current_term.data_type or "unknown"),
                "critical",
            ))

        # Check domain change
        if str(current_term.domain or "").lower() != str(previous_mapping.domain or "").lower():
            drifts.append((
                DriftType.DOMAIN_CHANGED,
                str(previous_mapping.domain or ""),
                str(current_term.domain or ""),
                "warning",
            ))

        # Check if deprecated
        if current_term.is_deprecated and not previous_mapping.is_current:
            drifts.append((
                DriftType.TERM_DEPRECATED,
                "active",
                "deprecated",
                "critical",
            ))

        # Check if renamed
        if str(current_term.name or "").lower() != str(previous_mapping.resolved_term_name or "").lower():
            drifts.append((
                DriftType.TERM_RENAMED,
                str(previous_mapping.resolved_term_name or ""),
                str(current_term.name or ""),
                "warning",
            ))

        if not drifts:
            return None

        # Return first drift (can have multiple but we report primary)
        drift_type, previous_val, current_val, severity = drifts[0]

        return TermDrift(
            drift_type=drift_type,
            alias_name=previous_mapping.alias_name,
            resolved_term_id=term_id,
            resolved_term_name=current_term.name,
            previous_value=previous_val,
            current_value=current_val,
            change_detected_at=datetime.utcnow(),
            severity=severity,
        )

    async def batch_detect_drift_for_term(
        self,
        term_id: str,
    ) -> List[RuleDrift]:
        """
        For a given term, find all rule versions affected.
        
        Returns list of RuleDrift for all rules using this term.
        """
        # Get all alias mappings for this term
        stmt = (
            select(AliasSourceMetadata)
            .where(
                (AliasSourceMetadata.resolved_term_id == term_id) &
                (AliasSourceMetadata.is_current == True) &
                (AliasSourceMetadata.source_type == 'catalog')
            )
        )
        result = await self.session.execute(stmt)
        mappings = result.scalars().all()

        affected_rules: List[RuleDrift] = []

        for mapping in mappings:
            rule_drift = await self.detect_drift_for_rule(
                mapping.rule_version_id.split('-')[0],  # Extract rule_id from rule_version_id
                mapping.rule_version_id,
            )

            if rule_drift:
                affected_rules.append(rule_drift)

        return affected_rules

    async def get_drift_summary_for_workspace(self) -> DriftSummary:
        """
        Get overall drift summary for entire workspace.
        
        Returns DriftSummary with aggregate statistics.
        """
        # Get all current business terms
        stmt = select(BusinessTerm).where(BusinessTerm.is_current == True)
        result = await self.session.execute(stmt)
        current_terms = result.scalars().all()

        affected_rules: List[RuleDrift] = []
        total_term_checks = len(current_terms)
        by_drift_type: Dict[str, int] = {}

        for term in current_terms:
            term_drift = await self.detect_drift_for_term(term.id)

            if term_drift:
                by_drift_type[term_drift.drift_type.value] = by_drift_type.get(
                    term_drift.drift_type.value, 0
                ) + 1

                # Find affected rules
                rule_drifts = await self.batch_detect_drift_for_term(term.id)
                affected_rules.extend(rule_drifts)

        # Deduplicate rules
        unique_rules = {}
        for rule_drift in affected_rules:
            key = (rule_drift.rule_id, rule_drift.rule_version_id)
            if key not in unique_rules:
                unique_rules[key] = rule_drift

        affected_rules = list(unique_rules.values())

        # Calculate statistics
        critical_count = len([
            d for rule in affected_rules
            for d in rule.drifts
            if d.severity == 'critical'
        ])
        warning_count = len([
            d for rule in affected_rules
            for d in rule.drifts
            if d.severity == 'warning'
        ])

        return DriftSummary(
            total_rules_checked=total_term_checks,
            rules_with_drift=len(affected_rules),
            total_drifts_detected=sum(r.total_drift_count for r in affected_rules),
            critical_drifts=critical_count,
            warning_drifts=warning_count,
            by_drift_type=by_drift_type,
            affected_rules=affected_rules,
        )

    async def _check_term_drift(
        self,
        resolved_term_id: str,
        alias_name: str,
        previous_term_name: str,
        previous_data_type: str,
    ) -> Optional[TermDrift]:
        """
        Internal helper to check if a term has drifted.
        
        Returns TermDrift if drift detected, None otherwise.
        """
        # Get current term definition
        stmt = select(BusinessTerm).where(BusinessTerm.id == resolved_term_id)
        current_term = await self.session.scalar(stmt)

        if not current_term:
            # Term was deleted
            return TermDrift(
                drift_type=DriftType.TERM_DEPRECATED,
                alias_name=alias_name,
                resolved_term_id=resolved_term_id,
                resolved_term_name=previous_term_name,
                previous_value="present",
                current_value="deleted",
                change_detected_at=datetime.utcnow(),
                severity="critical",
            )

        # Check datatype
        current_data_type = str(current_term.data_type or "unknown").lower()
        previous_type = str(previous_data_type or "unknown").lower()

        if current_data_type != previous_type:
            return TermDrift(
                drift_type=DriftType.DATA_TYPE_CHANGED,
                alias_name=alias_name,
                resolved_term_id=resolved_term_id,
                resolved_term_name=current_term.name,
                previous_value=previous_type,
                current_value=current_data_type,
                change_detected_at=datetime.utcnow(),
                severity="critical",
            )

        # Check if deprecated
        if current_term.is_deprecated:
            return TermDrift(
                drift_type=DriftType.TERM_DEPRECATED,
                alias_name=alias_name,
                resolved_term_id=resolved_term_id,
                resolved_term_name=current_term.name,
                previous_value="active",
                current_value="deprecated",
                change_detected_at=datetime.utcnow(),
                severity="critical",
            )

        # No drift detected
        return None


async def create_drift_detection_service(session: AsyncSession) -> DriftDetectionService:
    """Factory function to create drift detection service"""
    return DriftDetectionService(session)
