"""
Validator for business term guidelines (v1.0, 2026-02-20).
Checks business term definitions for compliance with semantic, structural, and governance rules.
"""
import re
from typing import List, Dict, Any

class BusinessTermGuidelineViolation(Exception):
    def __init__(self, violations: List[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


def validate_business_term_definition(term: str, definition: str, synonyms: List[str] = None) -> None:
    """
    Raises BusinessTermGuidelineViolation if the definition does not comply with the guidelines.
    """
    violations = []
    synonyms = synonyms or []
    
    # Guideline 1: Definition should start with a noun (or noun phrase, usually with 'A' or 'An')
    if not re.match(r"^(A|An) [A-Za-z]+", definition):
        violations.append("Definition should start with 'A' or 'An' followed by a noun (kick-off word)")

    # Guideline 2: Kick-off word should not be the term being defined
    if term.lower() in definition.lower().split():
        violations.append("Definition should not repeat the term being defined as the kick-off word")

    # Guideline 3: Definition should not be a synonym
    if definition.strip().lower() in [s.lower() for s in synonyms]:
        violations.append("Definition should not be a synonym of the term")

    # Guideline 6: Kick-off word should be singular
    if re.match(r"^(A|An) [A-Za-z]+s\b", definition):
        violations.append("Kick-off word should be singular, not plural")

    # Guideline 7: Should express the essence, not purpose/function/use
    if any(word in definition.lower() for word in ["used for", "serves to", "in order to", "for the purpose of"]):
        violations.append("Definition should express the essence, not purpose/function/use")

    # Guideline 9: Should not be a sentence (no subject/finite verb)
    if re.match(r"^[A-Z][^.]*\.$", definition) and (definition.count(" ") > 10):
        # Heuristic: long phrase with period may be a sentence
        violations.append("Definition should be a phrase, not a full sentence")

    # Guideline 10: Should not embed business rules
    if any(word in definition.lower() for word in ["must", "should", "shall", "required to"]):
        violations.append("Definition should not embed business rules")

    # Guideline 17: Should not be circular
    if term.lower() in definition.lower():
        violations.append("Definition should not be circular (should not include the term itself)")

    if violations:
        raise BusinessTermGuidelineViolation(violations)
