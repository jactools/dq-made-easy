import pytest
from app.application.services.business_term_guideline_validator import validate_business_term_definition, BusinessTermGuidelineViolation

def test_valid_definition():
    # Should pass: "A seat typically having four legs and a back for one person."
    validate_business_term_definition(
        term="Chair",
        definition="A seat typically having four legs and a back for one person.",
        synonyms=["Stool"]
    )

def test_definition_starts_with_verb():
    with pytest.raises(BusinessTermGuidelineViolation) as exc:
        validate_business_term_definition(
            term="Chair",
            definition="Sitting device for one person.",
            synonyms=[]
        )
    assert "start with 'A' or 'An'" in str(exc.value)

def test_definition_is_synonym():
    with pytest.raises(BusinessTermGuidelineViolation) as exc:
        validate_business_term_definition(
            term="Chair",
            definition="Stool",
            synonyms=["Stool"]
        )
    assert "should not be a synonym" in str(exc.value)

def test_definition_is_sentence():
    with pytest.raises(BusinessTermGuidelineViolation) as exc:
        validate_business_term_definition(
            term="Chair",
            definition="A chair is a seat typically having four legs and a back for one person.",
            synonyms=[]
        )
    assert "not repeat the term being defined" in str(exc.value)

def test_definition_is_plural():
    with pytest.raises(BusinessTermGuidelineViolation) as exc:
        validate_business_term_definition(
            term="Chairs",
            definition="A seats typically having four legs and a back for one person.",
            synonyms=[]
        )
    assert "should be singular" in str(exc.value)

def test_definition_embeds_business_rule():
    with pytest.raises(BusinessTermGuidelineViolation) as exc:
        validate_business_term_definition(
            term="Account",
            definition="A record that must be updated daily.",
            synonyms=[]
        )
    assert "should not embed business rules" in str(exc.value)

def test_definition_is_circular():
    with pytest.raises(BusinessTermGuidelineViolation) as exc:
        validate_business_term_definition(
            term="Account",
            definition="A account record.",
            synonyms=[]
        )
    assert "should not be circular" in str(exc.value)
