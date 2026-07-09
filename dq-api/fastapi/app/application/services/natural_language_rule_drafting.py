from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import re
from typing import Any

import httpx
from rapidfuzz import fuzz

from app.application.services.check_type_expression_generator import generate_expression_from_check_type
from app.application.services.registry_definition_resolver import RegistryDefinitionResolver
from app.domain.entities.rule_dsl_v2 import RuleDslV2Document
from app.domain.interfaces import DataCatalogRepository
from app.domain.interfaces import IncidentRepository
from app.domain.interfaces import ProfilingRepository


SUPPORTED_SEARCH_SCOPES = frozenset({"current", "all", "all_across_workspaces"})
SUPPORTED_CHECK_TYPES = frozenset({"UNIQUENESS", "PRESENT", "REGEX", "RANGE", "ALLOWLIST", "FRESHNESS"})
SUPPORTED_ANALYSIS_PROVIDERS = frozenset({"rapidfuzz", "llm"})
DEFAULT_LLM_SERVICE_URL = "https://dq-made-easy-llm:8000"
LLM_CA_BUNDLE_ENV = "DQ_LLM_CA_BUNDLE"

CHECK_TYPE_LABELS = {
    "UNIQUENESS": "Uniqueness",
    "PRESENT": "Present",
    "REGEX": "Format / Regex",
    "RANGE": "Range",
    "ALLOWLIST": "Allowlist",
    "FRESHNESS": "Freshness",
}

CHECK_TYPE_DIMENSIONS = {
    "UNIQUENESS": "Uniqueness",
    "PRESENT": "Completeness",
    "REGEX": "Validity",
    "RANGE": "Validity",
    "ALLOWLIST": "Validity",
    "FRESHNESS": "Timeliness",
}

_CATALOG_TERM_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "done",
    "for",
    "from",
    "had",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "least",
    "less",
    "lower",
    "max",
    "maximum",
    "minimum",
    "more",
    "may",
    "might",
    "must",
    "no",
    "not",
    "of",
    "on",
    "or",
    "over",
    "our",
    "percentages",
    "shall",
    "should",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "this",
    "to",
    "under",
    "below",
    "up",
    "upper",
    "was",
    "were",
    "when",
    "where",
    "which",
    "with",
    "within",
    "would",
    "above",
    "between",
    "equal",
    "equals",
    "greater",
    "most",
    "maximums",
    "minimums",
    "you",
    "your",
}

_CATALOG_TERM_SEARCH_THRESHOLD = 70.0


@dataclass(slots=True)
class CatalogAttributeRecord:
    attribute_id: str
    attribute_name: str
    version_id: str
    data_object_id: str
    data_object_name: str
    data_set_id: str
    data_set_name: str
    data_product_id: str
    data_product_name: str
    workspace_id: str
    parent_path: list[str]
    semantic_tags: list[str] = field(default_factory=list)
    current_context: bool = False


@dataclass(slots=True)
class ResolvedCandidate:
    attribute_id: str
    attribute_name: str
    version_id: str
    data_object_id: str
    data_object_name: str
    data_set_id: str
    data_set_name: str
    data_product_id: str
    data_product_name: str
    workspace_id: str
    parent_path: list[str]
    confidence_score: float
    match_reasons: list[str]
    current_context: bool
    match_roles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedCondition:
    attribute_term: str
    operator: str
    value: str
    raw_text: str
    remaining_prompt: str
    same_version_required: bool = True


@dataclass(slots=True)
class AuthorizedPreviewSearchScope:
    search_scope: str
    current_workspace_id: str
    allowed_workspace_ids: set[str]


class NaturalLanguageDraftingProviderError(RuntimeError):
    pass


class NaturalLanguageDraftingProviderUnavailableError(NaturalLanguageDraftingProviderError):
    pass


class NaturalLanguageDraftingProviderResponseError(NaturalLanguageDraftingProviderError):
    pass


def validate_natural_language_preview_inputs(*, prompt: str, current_workspace_id: str) -> tuple[str, str]:
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise ValueError("Preview prompt cannot be blank.")

    normalized_workspace_id = str(current_workspace_id or "").strip()
    if not normalized_workspace_id:
        raise ValueError("A current workspace is required to generate a preview.")

    return normalized_prompt, normalized_workspace_id


def _normalize_catalog_term_search_text(value: Any) -> str:
    tokens = [token for token in re.split(r"[^a-z0-9]+", str(value or "").lower()) if token]
    meaningful_tokens = [
        "percent" if token in {"percent", "percentage", "percentages"} else token
        for token in tokens
        if token not in _CATALOG_TERM_STOP_WORDS
    ]
    return " ".join(meaningful_tokens)


def _catalog_term_search_text(record: CatalogAttributeRecord) -> str:
    parts = [record.attribute_name, *record.parent_path]
    return " ".join(part for part in parts if part)


def _catalog_term_search_score(record: CatalogAttributeRecord, search: str) -> float:
    normalized_search = _normalize_catalog_term_search_text(search)
    if not normalized_search:
        return 0.0

    normalized_term = _normalize_catalog_term_search_text(_catalog_term_search_text(record))
    if not normalized_term:
        return 0.0

    overlap = set(normalized_search.split()) & set(normalized_term.split())
    score = max(
        float(fuzz.token_set_ratio(normalized_search, normalized_term)),
        float(fuzz.partial_ratio(normalized_search, normalized_term)),
    )
    if overlap:
        score = min(100.0, score + (10.0 * len(overlap)))
    return score


def _resolve_target_term_from_catalog(records: list[CatalogAttributeRecord], search: str) -> str:
    scored_records: list[tuple[float, str, CatalogAttributeRecord]] = []
    for record in records:
        score = _catalog_term_search_score(record, search)
        if score < _CATALOG_TERM_SEARCH_THRESHOLD:
            continue
        scored_records.append((score, record.attribute_name.lower(), record))

    scored_records.sort(key=lambda item: (-item[0], item[1]))
    if not scored_records:
        return ""
    return str(scored_records[0][2].attribute_name or "").strip()


def normalize_analysis_provider(value: Any) -> str:
    normalized_provider = str(value or "rapidfuzz").strip().lower()
    if normalized_provider not in SUPPORTED_ANALYSIS_PROVIDERS:
        raise ValueError(f"Unsupported analysis provider '{value}'.")
    return normalized_provider


def _build_llm_search_text(prompt: str, llm_rules: list[str]) -> str:
    search_parts = [str(prompt or "").strip()]
    search_parts.extend(str(rule or "").strip() for rule in llm_rules)
    return "\n".join(part for part in search_parts if part)


def _normalize_llm_rules(raw_rules: Any) -> list[str]:
    if raw_rules is None:
        raise NaturalLanguageDraftingProviderResponseError("LLM service response is missing rules.")

    if isinstance(raw_rules, str):
        stripped_rules = raw_rules.strip()
        if not stripped_rules:
            raise NaturalLanguageDraftingProviderResponseError("LLM service returned an empty rules payload.")

        try:
            parsed_rules = json.loads(stripped_rules)
        except json.JSONDecodeError:
            return [stripped_rules]

        raw_rules = parsed_rules

    if not isinstance(raw_rules, list):
        raise NaturalLanguageDraftingProviderResponseError("LLM service returned rules in an unsupported format.")

    normalized_rules = [str(rule or "").strip() for rule in raw_rules if str(rule or "").strip()]
    if not normalized_rules:
        raise NaturalLanguageDraftingProviderResponseError("LLM service returned an empty rules payload.")

    return normalized_rules


def _llm_service_client_kwargs(base_url: str) -> dict[str, Any]:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    if not normalized_base_url.lower().startswith("https://"):
        return {}

    ca_bundle = str(os.getenv(LLM_CA_BUNDLE_ENV, "")).strip()
    if not ca_bundle:
        raise NaturalLanguageDraftingProviderUnavailableError(
            f"HTTPS LLM service URLs require {LLM_CA_BUNDLE_ENV} to be configured."
        )

    return {"verify": ca_bundle}


def create_llm_service_client(*, base_url: str, timeout_seconds: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_seconds, **_llm_service_client_kwargs(base_url))


async def fetch_llm_rules(*, prompt: str, llm_service_url: str = DEFAULT_LLM_SERVICE_URL) -> list[str]:
    normalized_service_url = str(llm_service_url or "").strip().rstrip("/")
    if not normalized_service_url:
        raise NaturalLanguageDraftingProviderResponseError("LLM service URL is not configured.")

    try:
        async with create_llm_service_client(base_url=normalized_service_url, timeout_seconds=30.0) as client:
            response = await client.post(f"{normalized_service_url}/extract_rules", json={"text": prompt})
    except httpx.TimeoutException as exc:
        raise NaturalLanguageDraftingProviderUnavailableError(
            "The AI analysis service is taking longer than usual. Check Recent LLM Analysis Requests for progress or try again later."
        ) from exc
    except httpx.RequestError as exc:
        raise NaturalLanguageDraftingProviderUnavailableError(
            "The AI analysis service is unavailable right now. Try the local analysis engine or again later."
        ) from exc

    if response.status_code >= 400:
        raise NaturalLanguageDraftingProviderResponseError(
            f"LLM service returned HTTP {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise NaturalLanguageDraftingProviderResponseError("LLM service returned a non-JSON response.") from exc

    if not isinstance(payload, dict):
        raise NaturalLanguageDraftingProviderResponseError("LLM service returned an unsupported response payload.")

    return _normalize_llm_rules(payload.get("rules"))


def resolve_authorized_preview_search_scope(
    *,
    search_scope: str,
    current_workspace_id: str,
    accessible_workspace_ids: set[str],
) -> AuthorizedPreviewSearchScope:
    normalized_workspace_id = str(current_workspace_id or "").strip()
    if not normalized_workspace_id:
        raise ValueError("A current workspace is required to generate a preview.")
    if normalized_workspace_id not in accessible_workspace_ids:
        raise PermissionError("The current workspace is not available to the authenticated user.")

    normalized_scope = str(search_scope or "current").strip()
    if normalized_scope not in SUPPORTED_SEARCH_SCOPES:
        raise ValueError(f"Unsupported search scope '{search_scope}'.")
    if normalized_scope == "all_across_workspaces" and len(accessible_workspace_ids) <= 1:
        raise PermissionError("Cross-workspace attribute search is not available for this user.")

    allowed_workspace_ids = {normalized_workspace_id}
    if normalized_scope == "all_across_workspaces":
        allowed_workspace_ids = set(accessible_workspace_ids)

    return AuthorizedPreviewSearchScope(
        search_scope=normalized_scope,
        current_workspace_id=normalized_workspace_id,
        allowed_workspace_ids=allowed_workspace_ids,
    )


_STATUS_VALUE_HINTS = {"active", "inactive", "enabled", "disabled", "open", "closed"}
_IMPLICIT_REGEX_PATTERNS = {
    "email": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
    "email address": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
    "ssn": r"^\d{3}-\d{2}-\d{4}$",
    "social security": r"^\d{3}-\d{2}-\d{4}$",
    "social security number": r"^\d{3}-\d{2}-\d{4}$",
}
_RANGE_EXACT_PATTERN = re.compile(r"\b(?:equal(?:s|ed)?(?: to)?|exact(?:ly)?(?: to)?)\s+(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_RANGE_MIN_PATTERN = re.compile(
    r"\b(?:at least|min(?:imum)?|greater than(?: or equal to)?|more than(?: or equal to)?|no less than|above)\s+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_RANGE_MAX_PATTERN = re.compile(
    r"\b(?:at most|max(?:imum)?|less than(?: or equal to)?|lower than(?: or equal to)?|under|below|no more than|up to)\s+(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def infer_check_type(prompt: str) -> str | None:
    normalized_prompt = normalize_identifier(prompt)

    if re.search(r"\b(unique|uniqueness|duplicate|duplicates)\b", normalized_prompt):
        return "UNIQUENESS"
    if "valid" in normalized_prompt and re.search(r"\b(email|ssn|social security|iban|phone|postal|zip|postcode)\b", normalized_prompt):
        return "REGEX"
    if re.search(r"\b(present|required|not null|populated|filled)\b", normalized_prompt):
        return "PRESENT"
    if re.search(r"\b(regex|pattern|format|matches|match)\b", normalized_prompt):
        return "REGEX"
    if _RANGE_EXACT_PATTERN.search(normalized_prompt):
        return "RANGE"
    if re.search(r"\b(range|between|min|max|minimum|maximum|greater than|less than|lower than|under|below|above|more than|at least|at most|equal|equals|exactly)\b", normalized_prompt):
        return "RANGE"
    if re.search(r"\b(allowlist|allowed values|allowed|one of|enumeration|enum)\b", normalized_prompt):
        return "ALLOWLIST"
    if re.search(r"\b(fresh|freshness|stale|recent|older than|up to date|updated)\b", normalized_prompt):
        return "FRESHNESS"

    return None


def parse_prompt_condition(prompt: str) -> ParsedCondition | None:
    match = re.search(
        r"^\s*(?:if|when)\s+(?P<lhs>.+?)\s+is\s+(?P<value>`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z0-9_.-]+)\s*,?\s*(?P<tail>.+)$",
        str(prompt or "").strip(),
        re.IGNORECASE,
    )
    if not match:
        return None

    raw_lhs = str(match.group("lhs") or "").strip()
    raw_value = str(match.group("value") or "").strip()
    remaining_prompt = re.sub(r"^then\s+", "", str(match.group("tail") or "").strip(), flags=re.IGNORECASE)
    normalized_lhs = re.sub(r"^(?:a|an|the)\s+", "", raw_lhs, flags=re.IGNORECASE).strip()
    normalized_lhs_key = normalize_identifier(normalized_lhs)
    normalized_value = _strip_wrapping_quotes(raw_value)
    if normalized_lhs_key in {"customer", "record", "row", "entry", "user", "account"} and normalize_identifier(normalized_value) in _STATUS_VALUE_HINTS:
        normalized_lhs = "status"

    return ParsedCondition(
        attribute_term=normalized_lhs,
        operator="equals",
        value=normalized_value,
        raw_text=f"{raw_lhs} is {raw_value}",
        remaining_prompt=remaining_prompt,
    )


def extract_target_term(prompt: str, *, prompt_tail: str | None = None) -> str:
    source = re.sub(r"^then\s+", "", str(prompt_tail or prompt or "").strip(), flags=re.IGNORECASE)
    action_match = re.search(
        r"(?:valid\s+)?(?:a|an|the)?\s*(?P<term>[a-zA-Z][a-zA-Z0-9_. -]*?)(?:\s+address)?\s+must\s+be\s+(?:filled(?:\s+in)?|populated|required|present|valid)",
        source,
        re.IGNORECASE,
    )
    if action_match:
        return _normalize_extracted_term(str(action_match.group("term") or ""))

    explicit_match = re.search(r"`([^`]+)`|\"([^\"]+)\"|'([^']+)'", source)
    if explicit_match:
        return next((group.strip() for group in explicit_match.groups() if group), "")

    contextual_match = re.search(r"(?:attribute|column|field)\s+([a-zA-Z][a-zA-Z0-9_.-]*)", source, re.IGNORECASE)
    if contextual_match:
        return str(contextual_match.group(1) or "").strip()

    for_match = re.search(r"for\s+(?:attribute|column|field\s+)?([a-zA-Z][a-zA-Z0-9_.-]*)", source, re.IGNORECASE)
    if for_match:
        return str(for_match.group(1) or "").strip()

    identifier_match = re.search(r"\b[a-zA-Z]+_[a-zA-Z0-9_]+\b", source)
    if identifier_match:
        return str(identifier_match.group(0) or "").strip()

    return ""


def parse_prompt_parameter_hints(prompt: str, check_type: str, *, target_term: str = "") -> dict[str, Any]:
    if check_type == "UNIQUENESS":
        return {}

    if check_type == "PRESENT":
        return {"blockedValues": []}

    if check_type == "REGEX":
        slash_match = re.search(r"/([^/]+)/([a-z]*)", prompt)
        if slash_match:
            payload: dict[str, Any] = {"pattern": slash_match.group(1)}
            if slash_match.group(2):
                payload["flags"] = slash_match.group(2)
            return payload

        quoted_match = re.search(r"(?:regex|pattern|matches)\s+(?:pattern\s+)?(?:`([^`]+)`|\"([^\"]+)\"|'([^']+)')", prompt, re.IGNORECASE)
        pattern = next((group.strip() for group in quoted_match.groups() if group), "") if quoted_match else ""
        if pattern:
            return {"pattern": pattern}
        implicit_pattern = _infer_implicit_regex_pattern(prompt, target_term)
        if implicit_pattern:
            payload = {"pattern": implicit_pattern}
            if _prompt_requires_present(prompt):
                payload["requirePresent"] = True
            return payload
        raise ValueError("REGEX preview requires an explicit pattern such as /.../ or a quoted pattern.")

    if check_type == "RANGE":
        exact_match = _RANGE_EXACT_PATTERN.search(prompt)
        if exact_match:
            exact_value = _coerce_number(exact_match.group(1))
            return {
                "minValue": exact_value,
                "maxValue": exact_value,
                "inclusive": True,
            }

        between_match = re.search(
            r"(?:between|from)\s+(-?\d+(?:\.\d+)?)\s+(?:and|to)\s+(-?\d+(?:\.\d+)?)",
            prompt,
            re.IGNORECASE,
        )
        if between_match:
            return {
                "minValue": _coerce_number(between_match.group(1)),
                "maxValue": _coerce_number(between_match.group(2)),
                "inclusive": True,
            }

        min_match = re.search(r"(?:at least|min(?:imum)?|greater than(?: or equal to)?|more than(?: or equal to)?|no less than|above)\s+(-?\d+(?:\.\d+)?)", prompt, re.IGNORECASE)
        max_match = _RANGE_MAX_PATTERN.search(prompt)
        if min_match or max_match:
            min_value = _coerce_number(min_match.group(1)) if min_match else None
            max_value = _coerce_number(max_match.group(1)) if max_match else None
            inclusive = True
            if min_match:
                min_text = min_match.group(0).lower()
                inclusive = inclusive and bool(
                    re.search(r"\b(?:at least|min(?:imum)?|greater than or equal to|more than or equal to|no less than)\b", min_text)
                )
            if max_match:
                max_text = max_match.group(0).lower()
                inclusive = inclusive and bool(
                    re.search(r"\b(?:at most|max(?:imum)?|less than or equal to|lower than or equal to|no more than|up to)\b", max_text)
                )
            return {
                "minValue": min_value,
                "maxValue": max_value,
                "inclusive": inclusive,
            }

        raise ValueError("RANGE preview requires numeric bounds such as 'between 1 and 10' or 'at least 18'.")

    if check_type == "ALLOWLIST":
        marker_match = re.search(r"(?:one of|allowed values(?: are|:)?|allowlist(?: is|:)?)\s+(.+)$", prompt, re.IGNORECASE)
        if not marker_match:
            raise ValueError("ALLOWLIST preview requires explicit allowed values such as 'one of A, B, C'.")

        raw_values = str(marker_match.group(1) or "").strip().rstrip(".")
        if not raw_values or not re.search(r",|\bor\b|\band\b|\[", raw_values, re.IGNORECASE):
            raise ValueError("ALLOWLIST preview requires explicit allowed values such as 'one of A, B, C'.")

        normalized_values = [
            _strip_wrapping_quotes(item)
            for item in re.split(r",|\bor\b|\band\b", raw_values, flags=re.IGNORECASE)
        ]
        allowed_values = [item for item in normalized_values if item]
        if not allowed_values:
            raise ValueError("ALLOWLIST preview requires at least one allowed value.")
        return {"allowedValues": allowed_values, "caseSensitive": False}

    if check_type == "FRESHNESS":
        days_match = re.search(r"(\d+)\s+day", prompt, re.IGNORECASE)
        if not days_match:
            raise ValueError("FRESHNESS preview requires an explicit day limit such as 'older than 2 days'.")
        return {"maxDaysOld": int(days_match.group(1)), "anchor": "now"}

    raise ValueError(f"Unsupported check type '{check_type}'.")


def build_catalog_records(
    repository: DataCatalogRepository,
    *,
    current_workspace_id: str,
) -> list[CatalogAttributeRecord]:
    products = {str(row.id or ""): row for row in repository.list_data_products()}
    data_sets = {str(row.id or ""): row for row in repository.list_data_sets()}
    data_objects = {str(row.id or ""): row for row in repository.list_data_objects_catalog(None)}

    records: list[CatalogAttributeRecord] = []
    for attribute in repository.list_attributes_catalog(None):
        data_object = data_objects.get(str(attribute.data_object_id or ""))
        if data_object is None:
            continue

        data_set = data_sets.get(str(data_object.dataset_id or ""))
        data_product = products.get(str(data_set.product_id or "")) if data_set is not None else None
        workspace_id = str((data_set.workspace_id if data_set is not None else "") or (data_product.workspace_id if data_product is not None else "") or "").strip()
        if not workspace_id:
            continue

        parent_path = [
            str(data_product.name or "").strip() if data_product is not None else "",
            str(data_set.name or "").strip() if data_set is not None else "",
            str(data_object.name or "").strip(),
        ]
        parent_path = [segment for segment in parent_path if segment]

        records.append(
            CatalogAttributeRecord(
                attribute_id=str(attribute.id or ""),
                attribute_name=str(attribute.name or "").strip() or str(attribute.id or ""),
                version_id=str(attribute.version_id or ""),
                data_object_id=str(attribute.data_object_id or ""),
                data_object_name=str(data_object.name or "").strip(),
                data_set_id=str(data_set.id or "") if data_set is not None else "",
                data_set_name=str(data_set.name or "").strip() if data_set is not None else "",
                data_product_id=str(data_product.id or "") if data_product is not None else "",
                data_product_name=str(data_product.name or "").strip() if data_product is not None else "",
                workspace_id=workspace_id,
                parent_path=parent_path,
                semantic_tags=_infer_semantic_tags(
                    attribute_name=str(attribute.name or ""),
                    parent_path=parent_path,
                    attribute_type=str(attribute.type or ""),
                    is_primary_key=bool(attribute.is_primary_key),
                    is_business_key=bool(attribute.is_business_key),
                ),
                current_context=workspace_id == current_workspace_id,
            )
        )

    return records


def resolve_candidates(
    records: list[CatalogAttributeRecord],
    *,
    check_type: str,
    target_term: str,
    search_scope: str,
    current_workspace_id: str,
    allowed_workspace_ids: set[str],
) -> list[ResolvedCandidate]:
    normalized_target = normalize_identifier(target_term)
    target_tokens = {token for token in normalized_target.split(" ") if token}

    filtered_records = [
        record
        for record in records
        if _record_in_scope(
            record,
            search_scope=search_scope,
            current_workspace_id=current_workspace_id,
            allowed_workspace_ids=allowed_workspace_ids,
        )
    ]

    candidates: list[ResolvedCandidate] = []
    for record in filtered_records:
        score = 0.0
        reasons: list[str] = []
        normalized_name = normalize_identifier(record.attribute_name)
        normalized_parent = normalize_identifier(" ".join(record.parent_path))

        if normalized_name == normalized_target:
            score += 0.65
            reasons.append("Exact attribute-name match")
        elif normalized_target and (normalized_name.startswith(normalized_target) or normalized_target in normalized_name or normalized_name in normalized_target):
            score += 0.45
            reasons.append("Partial attribute-name match")

        matched_tags = [tag for tag in record.semantic_tags if normalize_identifier(tag) in target_tokens]
        if matched_tags:
            score += 0.15
            reasons.append("Semantic tag match")

        target_root = next(iter(target_tokens), "")
        if target_root and target_root in normalized_parent:
            score += 0.10
            reasons.append("Parent context matches target concept")

        if record.current_context:
            score += 0.05
            reasons.append("In current workspace context")

        if check_type == "UNIQUENESS" and "identifier" in record.semantic_tags:
            score += 0.05
            reasons.append("Identifier-like attribute for uniqueness")
        if check_type == "REGEX" and "format" in record.semantic_tags:
            score += 0.05
            reasons.append("Format-oriented attribute")
        if check_type == "ALLOWLIST" and "allowlist" in record.semantic_tags:
            score += 0.05
            reasons.append("Coded-value attribute")
        if check_type == "FRESHNESS" and "freshness" in record.semantic_tags:
            score += 0.05
            reasons.append("Timestamp-like freshness attribute")
        if check_type == "RANGE" and "range" in record.semantic_tags:
            score += 0.05
            reasons.append("Range-oriented attribute")

        if score <= 0:
            continue

        candidates.append(
            ResolvedCandidate(
                attribute_id=record.attribute_id,
                attribute_name=record.attribute_name,
                version_id=record.version_id,
                data_object_id=record.data_object_id,
                data_object_name=record.data_object_name,
                data_set_id=record.data_set_id,
                data_set_name=record.data_set_name,
                data_product_id=record.data_product_id,
                data_product_name=record.data_product_name,
                workspace_id=record.workspace_id,
                parent_path=list(record.parent_path),
                confidence_score=min(0.99, round(score, 2)),
                match_reasons=reasons,
                current_context=record.current_context,
                match_roles=[],
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.confidence_score,
            0 if item.workspace_id == current_workspace_id else 1,
            ".".join(item.parent_path),
            item.attribute_name,
        )
    )
    return candidates[:25]


def resolve_preview_candidates(
    records: list[CatalogAttributeRecord],
    *,
    check_type: str,
    target_term: str,
    search_scope: str,
    current_workspace_id: str,
    allowed_workspace_ids: set[str],
    condition: ParsedCondition | None,
) -> list[ResolvedCandidate]:
    raw_target_candidates = resolve_candidates(
        records,
        check_type=check_type,
        target_term=target_term,
        search_scope=search_scope,
        current_workspace_id=current_workspace_id,
        allowed_workspace_ids=allowed_workspace_ids,
    )
    target_candidates = [candidate for candidate in raw_target_candidates if _candidate_matches_term(candidate, target_term)]
    if not target_candidates:
        target_candidates = raw_target_candidates[:5]
    candidate_map: dict[str, ResolvedCandidate] = {}
    for candidate in target_candidates:
        candidate.match_roles = ["target"]
        candidate_map[candidate.attribute_id] = candidate

    if condition is not None:
        raw_condition_candidates = resolve_candidates(
            records,
            check_type="ALLOWLIST",
            target_term=condition.attribute_term,
            search_scope=search_scope,
            current_workspace_id=current_workspace_id,
            allowed_workspace_ids=allowed_workspace_ids,
        )
        condition_candidates = [candidate for candidate in raw_condition_candidates if _candidate_matches_term(candidate, condition.attribute_term)]
        if not condition_candidates:
            condition_candidates = raw_condition_candidates[:5]
        for candidate in condition_candidates:
            existing = candidate_map.get(candidate.attribute_id)
            if existing is None:
                candidate.match_roles = ["condition"]
                candidate_map[candidate.attribute_id] = candidate
                continue
            existing.match_roles = sorted(set([*existing.match_roles, "condition"]))
            existing.confidence_score = max(existing.confidence_score, candidate.confidence_score)
            existing.match_reasons = sorted(set([*existing.match_reasons, *candidate.match_reasons]))

    candidates = list(candidate_map.values())
    candidates.sort(
        key=lambda item: (
            0 if "target" in item.match_roles else 1,
            -item.confidence_score,
            0 if item.workspace_id == current_workspace_id else 1,
            ".".join(item.parent_path),
            item.attribute_name,
        )
    )
    return candidates[:25]


def build_ranked_preview_candidate_attributes(
    *,
    catalog_repository: DataCatalogRepository,
    check_type: str,
    target_term: str,
    search_scope: str,
    current_workspace_id: str,
    allowed_workspace_ids: set[str],
    condition: ParsedCondition | None = None,
) -> list[dict[str, Any]]:
    resolved_scope = resolve_authorized_preview_search_scope(
        search_scope=search_scope,
        current_workspace_id=current_workspace_id,
        accessible_workspace_ids=allowed_workspace_ids,
    )
    catalog_records = build_catalog_records(catalog_repository, current_workspace_id=current_workspace_id)
    candidates = resolve_preview_candidates(
        catalog_records,
        check_type=check_type,
        target_term=target_term,
        search_scope=resolved_scope.search_scope,
        current_workspace_id=resolved_scope.current_workspace_id,
        allowed_workspace_ids=resolved_scope.allowed_workspace_ids,
        condition=condition,
    )
    return [serialize_candidate(candidate) for candidate in candidates]


def build_natural_language_rule_preview_payload(
    *,
    prompt: str,
    search_scope: str,
    current_workspace_id: str,
    accessible_workspace_ids: set[str],
    catalog_repository: DataCatalogRepository,
    target_term_search_text: str | None = None,
) -> dict[str, Any]:
    normalized_prompt, normalized_workspace_id = validate_natural_language_preview_inputs(
        prompt=prompt,
        current_workspace_id=current_workspace_id,
    )
    resolved_scope = resolve_authorized_preview_search_scope(
        search_scope=search_scope,
        current_workspace_id=normalized_workspace_id,
        accessible_workspace_ids=accessible_workspace_ids,
    )

    check_type = infer_check_type(normalized_prompt)
    if not check_type:
        raise ValueError("This feature currently supports uniqueness, present, regex, range, allowlist, and freshness checks only.")

    parsed_condition = parse_prompt_condition(normalized_prompt)
    target_term = extract_target_term(normalized_prompt, prompt_tail=parsed_condition.remaining_prompt if parsed_condition else None)
    catalog_records = build_catalog_records(catalog_repository, current_workspace_id=resolved_scope.current_workspace_id)
    if not catalog_records:
        raise ValueError("Preview metadata dependencies are unavailable. Load catalog metadata before generating a preview.")
    if not target_term:
        target_term = _resolve_target_term_from_catalog(catalog_records, target_term_search_text or normalized_prompt)
    if not target_term:
        raise ValueError("Mention the attribute, column, or field you want to check so candidate resolution can run.")

    parse_prompt_parameter_hints(normalized_prompt, check_type, target_term=target_term)
    candidate_attributes = build_ranked_preview_candidate_attributes(
        catalog_repository=catalog_repository,
        check_type=check_type,
        target_term=target_term,
        search_scope=resolved_scope.search_scope,
        current_workspace_id=resolved_scope.current_workspace_id,
        allowed_workspace_ids=accessible_workspace_ids,
        condition=parsed_condition,
    )

    return {
        "success": True,
        "target_terms": [target_term],
        "search_scope": resolved_scope.search_scope,
        "candidate_attributes": candidate_attributes,
        "parsed_condition": None if parsed_condition is None else {
            "attribute_term": parsed_condition.attribute_term,
            "operator": parsed_condition.operator,
            "value": parsed_condition.value,
            "same_version_required": parsed_condition.same_version_required,
        },
        "requires_steward_confirmation": True,
        "draft_rule_preview": {
            "name": build_draft_name(
                check_type=check_type,
                target_term=target_term,
                selected_candidates=[deserialize_candidate(candidate) for candidate in candidate_attributes],
                condition=parsed_condition,
            ),
            "workspace_id": resolved_scope.current_workspace_id,
            "dimension": CHECK_TYPE_DIMENSIONS[check_type],
            "dsl": build_preview_rule_dsl_v2_document(
                prompt=normalized_prompt,
                check_type=check_type,
                selected_candidates=[deserialize_candidate(candidate) for candidate in candidate_attributes],
                condition=parsed_condition,
            ),
            "summary": (
                f"Select one or more candidate attributes to create a {CHECK_TYPE_LABELS[check_type].lower()} draft suggestion."
                if parsed_condition is None
                else f"Select one target attribute and one condition attribute from the same data object version to create a conditional {CHECK_TYPE_LABELS[check_type].lower()} draft suggestion."
            ),
        },
    }


def _format_preview_signal_items(values: list[object], *, attribute_name: str) -> list[str]:
    items: list[str] = []
    for value in values:
        text = str(getattr(value, attribute_name, value) or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _summarize_preview_signals(*, metadata_facts: dict[str, Any]) -> str:
    signal_sources = [str(value) for value in metadata_facts.get("signal_sources") or [] if str(value).strip()]
    if not signal_sources:
        return ""
    readable_sources = ", ".join(signal_sources)
    return f"The preview considered {readable_sources} as supporting metadata signals."


async def build_natural_language_rule_preview_payload_for_provider(
    *,
    prompt: str,
    search_scope: str,
    current_workspace_id: str,
    accessible_workspace_ids: set[str],
    catalog_repository: DataCatalogRepository,
    analysis_provider: str,
    llm_service_url: str = DEFAULT_LLM_SERVICE_URL,
    current_user_id: str | None = None,
    registry_definition_resolver: RegistryDefinitionResolver | None = None,
    profiling_repository: ProfilingRepository | None = None,
    incident_repository: IncidentRepository | None = None,
) -> dict[str, Any]:
    normalized_provider = normalize_analysis_provider(analysis_provider)
    if normalized_provider == "rapidfuzz":
        payload = build_natural_language_rule_preview_payload(
            prompt=prompt,
            search_scope=search_scope,
            current_workspace_id=current_workspace_id,
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=catalog_repository,
        )
    else:
        normalized_prompt, _ = validate_natural_language_preview_inputs(prompt=prompt, current_workspace_id=current_workspace_id)
        llm_rules = await fetch_llm_rules(prompt=normalized_prompt, llm_service_url=llm_service_url)
        llm_search_text = _build_llm_search_text(normalized_prompt, llm_rules)

        payload = build_natural_language_rule_preview_payload(
            prompt=normalized_prompt,
            search_scope=search_scope,
            current_workspace_id=current_workspace_id,
            accessible_workspace_ids=accessible_workspace_ids,
            catalog_repository=catalog_repository,
            target_term_search_text=llm_search_text,
        )

    if registry_definition_resolver is None and profiling_repository is None and incident_repository is None:
        return payload

    normalized_prompt, normalized_workspace_id = validate_natural_language_preview_inputs(
        prompt=prompt,
        current_workspace_id=current_workspace_id,
    )
    enriched_facts = dict(payload.get("metadata_facts") or {})
    signal_sources: list[str] = ["schema", "tags"]

    if registry_definition_resolver is not None:
        glossary_terms = await registry_definition_resolver.list_definitions(
            query=normalized_prompt,
            limit=5,
        )
        glossary_hits = [
            str(item.get("definition_name") or item.get("name") or item.get("definition_id") or "").strip()
            for item in glossary_terms
            if str(item.get("definition_name") or item.get("name") or item.get("definition_id") or "").strip()
        ]
        if glossary_hits:
            signal_sources.append("glossary_terms")
            enriched_facts["glossary_term_hits"] = glossary_hits
            enriched_facts["glossary_term_count"] = len(glossary_hits)

    if profiling_repository is not None and current_user_id:
        profiling_requests = profiling_repository.list_profiling_requests(
            user_id=current_user_id,
            data_source_id=None,
            limit=5,
        )
        if profiling_requests:
            signal_sources.append("profiling_requests")
            enriched_facts["profiling_request_count"] = len(profiling_requests)
            enriched_facts["profiling_request_statuses"] = _format_preview_signal_items(
                profiling_requests,
                attribute_name="status",
            )

    if incident_repository is not None:
        incidents = incident_repository.list_incidents(
            workspace_id=normalized_workspace_id,
            limit=5,
        )
        root_cause_suggestions = incident_repository.list_root_cause_suggestions(
            workspace_id=normalized_workspace_id,
            limit=5,
        )
        if incidents or root_cause_suggestions:
            signal_sources.append("historical_incidents")
            enriched_facts["incident_count"] = len(incidents)
            enriched_facts["incident_kinds"] = _format_preview_signal_items(
                incidents,
                attribute_name="incident_kind",
            )
            enriched_facts["incident_statuses"] = _format_preview_signal_items(
                incidents,
                attribute_name="status",
            )
            enriched_facts["incident_root_cause_suggestion_count"] = len(root_cause_suggestions)

    enriched_facts["signal_sources"] = signal_sources
    payload["metadata_facts"] = enriched_facts
    metadata_summary = _summarize_preview_signals(metadata_facts=enriched_facts) or payload.get("metadata_summary")
    payload["metadata_summary"] = metadata_summary
    if payload.get("explanation"):
        payload["explanation"] = f"{payload['explanation']} {metadata_summary}".strip()
    else:
        payload["explanation"] = metadata_summary

    return payload


def build_natural_language_rule_draft_suggestion_payload(
    *,
    prompt: str,
    search_scope: str,
    current_workspace_id: str,
    selected_attribute_ids: list[str],
    preview_payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_prompt, normalized_workspace_id = validate_natural_language_preview_inputs(
        prompt=prompt,
        current_workspace_id=current_workspace_id,
    )
    selected_ids = [str(value or "").strip() for value in selected_attribute_ids if str(value or "").strip()]
    if not selected_ids:
        raise ValueError("Select at least one candidate attribute before creating a draft suggestion.")

    candidate_payloads = list(preview_payload.get("candidate_attributes") or [])
    if not candidate_payloads:
        raise ValueError("Preview metadata dependencies are unavailable. Load catalog metadata before creating a draft suggestion.")

    candidate_map = {
        str(candidate.get("attribute_id") or "").strip(): candidate
        for candidate in candidate_payloads
        if str(candidate.get("attribute_id") or "").strip()
    }
    if any(selected_id not in candidate_map for selected_id in selected_ids):
        raise ValueError("One or more selected attributes are no longer valid for this preview scope.")

    selected_candidates = [
        deserialize_candidate(candidate_map[selected_id])
        for selected_id in selected_ids
    ]

    selected_object_versions = {
        (candidate.data_object_id, candidate.version_id)
        for candidate in selected_candidates
    }
    if len(selected_object_versions) > 1:
        raise ValueError("Selected attributes must all come from the same data object version before creating a draft suggestion.")

    check_type = infer_check_type(normalized_prompt)
    if not check_type:
        raise ValueError("This feature currently supports uniqueness, present, regex, range, allowlist, and freshness checks only.")

    parsed_condition = parse_prompt_condition(normalized_prompt)
    target_term = str((preview_payload.get("target_terms") or [""])[0] or "")
    check_type_params = build_check_type_params(
        prompt=normalized_prompt,
        check_type=check_type,
        selected_candidates=selected_candidates,
        condition=parsed_condition,
    )
    expression = generate_expression_from_check_type(check_type, check_type_params)
    draft_name = build_draft_name(
        check_type=check_type,
        target_term=target_term,
        selected_candidates=selected_candidates,
        condition=parsed_condition,
    )
    selected_attribute_snapshots = [serialize_candidate(candidate) for candidate in selected_candidates]
    parent_context_snapshot = [
        {
            "attribute_id": candidate.attribute_id,
            "workspace_id": candidate.workspace_id,
            "parent_path": list(candidate.parent_path),
            "data_object_id": candidate.data_object_id,
            "data_object_name": candidate.data_object_name,
            "data_set_id": candidate.data_set_id,
            "data_set_name": candidate.data_set_name,
            "data_product_id": candidate.data_product_id,
            "data_product_name": candidate.data_product_name,
            "current_context": candidate.current_context,
        }
        for candidate in selected_candidates
    ]

    return {
        "data_source_id": f"nl-preview:{current_workspace_id}",
        "suggested_rule": {
            "name": draft_name,
            "description": f"Created from natural-language request '{normalized_prompt}'.",
            "expression": expression,
            "dimension": CHECK_TYPE_DIMENSIONS[check_type],
            "rule_type": check_type,
            "check_type": check_type,
            "check_type_params": check_type_params,
            "workspace_id": normalized_workspace_id,
            "target_terms": [target_term],
            "search_scope": search_scope,
            "parsed_condition": preview_payload.get("parsed_condition"),
            "selected_attribute_ids": selected_ids,
            "selected_attributes": selected_attribute_snapshots,
            "parent_context_snapshot": parent_context_snapshot,
            "draft_summary": build_draft_summary(check_type=check_type, selected_candidates=selected_candidates, condition=parsed_condition),
            "dsl": build_preview_rule_dsl_v2_document(
                prompt=prompt,
                check_type=check_type,
                selected_candidates=selected_candidates,
                condition=parsed_condition,
            ),
            "prompt": normalized_prompt,
            "original_prompt_text": prompt,
        },
        "confidence_score": round(sum(candidate.confidence_score for candidate in selected_candidates) / len(selected_candidates), 2),
        "reason": f"Natural-language draft created from {search_scope} scope after steward confirmation.",
        "rule_type": check_type,
    }


def build_check_type_params(
    *,
    prompt: str,
    check_type: str,
    selected_candidates: list[ResolvedCandidate],
    condition: ParsedCondition | None = None,
) -> dict[str, Any]:
    if not selected_candidates:
        raise ValueError("Select at least one candidate attribute before creating a draft suggestion.")

    target_candidates = [candidate for candidate in selected_candidates if "target" in candidate.match_roles] if condition else list(selected_candidates)
    condition_candidates = [candidate for candidate in selected_candidates if "condition" in candidate.match_roles] if condition else []

    if condition is not None:
        if len(target_candidates) != 1:
            raise ValueError("Conditional draft creation requires exactly one selected target attribute.")
        if len(condition_candidates) != 1:
            raise ValueError("Conditional draft creation requires exactly one selected condition attribute.")
        if target_candidates[0].version_id != condition_candidates[0].version_id:
            raise ValueError("Conditional draft creation requires the condition and target attributes to come from the same data object version.")

    attribute_names = _dedupe_attribute_names(target_candidates)
    parameter_hints = parse_prompt_parameter_hints(prompt, check_type, target_term=attribute_names[0] if attribute_names else "")
    condition_payload = None
    if condition is not None:
        condition_payload = {
            "attribute": condition_candidates[0].attribute_name,
            "operator": condition.operator,
            "value": condition.value,
        }

    if check_type == "UNIQUENESS":
        return {"attributes": attribute_names}
    if check_type == "PRESENT":
        _require_single_attribute(attribute_names, check_type=check_type)
        payload = {
            "attribute": attribute_names[0],
            "blockedValues": list(parameter_hints.get("blockedValues") or []),
            "caseSensitive": bool(parameter_hints.get("caseSensitive", False)),
        }
        if condition_payload is not None:
            payload["condition"] = condition_payload
        return payload
    if check_type == "REGEX":
        _require_single_attribute(attribute_names, check_type=check_type)
        payload = {"attribute": attribute_names[0], "pattern": parameter_hints["pattern"]}
        if parameter_hints.get("flags"):
            payload["flags"] = parameter_hints["flags"]
        if parameter_hints.get("requirePresent"):
            payload["requirePresent"] = True
        if condition_payload is not None:
            payload["condition"] = condition_payload
        return payload
    if check_type == "RANGE":
        _require_single_attribute(attribute_names, check_type=check_type)
        payload = {
            "attribute": attribute_names[0],
            "minValue": parameter_hints.get("minValue"),
            "maxValue": parameter_hints.get("maxValue"),
            "inclusive": bool(parameter_hints.get("inclusive", True)),
        }
        if condition_payload is not None:
            payload["condition"] = condition_payload
        return payload
    if check_type == "ALLOWLIST":
        _require_single_attribute(attribute_names, check_type=check_type)
        payload = {
            "attribute": attribute_names[0],
            "allowedValues": list(parameter_hints.get("allowedValues") or []),
            "caseSensitive": bool(parameter_hints.get("caseSensitive", False)),
        }
        if condition_payload is not None:
            payload["condition"] = condition_payload
        return payload
    if check_type == "FRESHNESS":
        _require_single_attribute(attribute_names, check_type=check_type)
        payload = {
            "attribute": attribute_names[0],
            "maxDaysOld": int(parameter_hints["maxDaysOld"]),
            "anchor": str(parameter_hints.get("anchor") or "now"),
        }
        if condition_payload is not None:
            payload["condition"] = condition_payload
        return payload

    raise ValueError(f"Unsupported check type '{check_type}'.")


def build_preview_rule_dsl_v2_document(
    *,
    prompt: str,
    check_type: str,
    selected_candidates: list[ResolvedCandidate],
    condition: ParsedCondition | None = None,
) -> dict[str, Any]:
    if not selected_candidates:
        raise ValueError("Select at least one candidate attribute before creating a draft suggestion.")

    target_candidates = [candidate for candidate in selected_candidates if "target" in candidate.match_roles] if condition else list(selected_candidates)
    condition_candidates = [candidate for candidate in selected_candidates if "condition" in candidate.match_roles] if condition else []
    target_attribute_names = _dedupe_attribute_names(target_candidates)
    if not target_attribute_names:
        raise ValueError("Select at least one target attribute before creating a draft suggestion.")

    parameter_hints = parse_prompt_parameter_hints(prompt, check_type, target_term=target_attribute_names[0])

    condition_payload = None
    if condition is not None and condition_candidates:
        condition_payload = {
            "attribute": condition_candidates[0].attribute_name,
            "operator": condition.operator,
            "value": condition.value,
        }

    primary_candidate = target_candidates[0]
    if not primary_candidate.data_object_id:
        raise ValueError("Selected candidate attributes must include a data object identifier.")

    scope: dict[str, Any] = {
        "dataset": {
            "data_object_id": primary_candidate.data_object_id,
        }
    }

    if check_type in {"REGEX", "RANGE", "ALLOWLIST", "PRESENT"}:
        check_type_params: dict[str, Any] = {
            "attribute": target_attribute_names[0],
            **parameter_hints,
        }
        if condition_payload is not None:
            check_type_params["condition"] = condition_payload
        rule = {
            "kind": "row_assertion",
            "scope": scope,
            "measure": {
                "type": "row_predicate",
                "predicate": {
                    "kind": "row_predicate",
                    "language": "dq_predicate",
                    "expression": generate_expression_from_check_type(check_type, check_type_params),
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": "gte",
                "value": 100,
                "unit": "percent",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        }
    elif check_type == "UNIQUENESS":
        rule = {
            "kind": "metric_threshold",
            "scope": scope,
            "measure": {
                "type": "metric",
                "metric": "duplicate_count",
                "subject": {
                    "columns": target_attribute_names,
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": "lte",
                "value": 0,
                "unit": "count",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        }
    elif check_type == "FRESHNESS":
        check_type_params = {
            "attribute": target_attribute_names[0],
            "maxDaysOld": int(parameter_hints["maxDaysOld"]),
            "anchor": str(parameter_hints.get("anchor") or "now"),
        }
        if condition_payload is not None:
            check_type_params["condition"] = condition_payload
        rule = {
            "kind": "freshness_assertion",
            "scope": scope,
            "measure": {
                "type": "metric",
                "metric": "freshness_age",
                "subject": {
                    "column": target_attribute_names[0],
                },
            },
            "expectation": {
                "type": "threshold",
                "operator": "lte",
                "value": int(check_type_params["maxDaysOld"]),
                "unit": "duration",
            },
            "evidence": {
                "failed_rows": {
                    "mode": "sample",
                    "limit": 25,
                    "include_row_identifier": True,
                    "include_primary_key": True,
                },
                "emit_compiled_artifact": True,
                "emit_generated_sql": False,
            },
            "operations": {
                "severity": "critical",
                "preferred_engines": ["gx", "sql"],
                "fail_if_not_native": False,
            },
        }
    else:
        raise ValueError(f"Unsupported check type '{check_type}'.")

    draft_document = RuleDslV2Document.model_validate({
        "schema_version": "2.0.0",
        "rule": rule,
    })
    return draft_document.model_dump(by_alias=True, mode="json")


def build_draft_name(*, check_type: str, target_term: str, selected_candidates: list[ResolvedCandidate], condition: ParsedCondition | None = None) -> str:
    selected_attribute_names = _dedupe_attribute_names(
        [candidate for candidate in selected_candidates if "target" in candidate.match_roles]
        if condition is not None
        else selected_candidates,
    )
    target_label = " + ".join(selected_attribute_names[:3]) if selected_attribute_names else target_term
    if condition is None:
        return f"{CHECK_TYPE_LABELS.get(check_type, check_type.title())} draft for {target_label}"
    return f"{CHECK_TYPE_LABELS.get(check_type, check_type.title())} draft for {target_label} when {condition.attribute_term} = {condition.value}"


def build_draft_summary(*, check_type: str, selected_candidates: list[ResolvedCandidate], condition: ParsedCondition | None = None) -> str:
    if check_type == "UNIQUENESS" and len(_dedupe_attribute_names(selected_candidates)) > 1:
        return "Composite uniqueness draft"
    if condition is not None:
        return f"Conditional {CHECK_TYPE_LABELS.get(check_type, check_type.title()).lower()} draft"
    return f"{CHECK_TYPE_LABELS.get(check_type, check_type.title())} draft"


def serialize_candidate(candidate: ResolvedCandidate) -> dict[str, Any]:
    return {
        "attribute_id": candidate.attribute_id,
        "attribute_name": candidate.attribute_name,
        "version_id": candidate.version_id,
        "data_object_id": candidate.data_object_id,
        "data_object_name": candidate.data_object_name,
        "data_set_id": candidate.data_set_id,
        "data_set_name": candidate.data_set_name,
        "data_product_id": candidate.data_product_id,
        "data_product_name": candidate.data_product_name,
        "workspace_id": candidate.workspace_id,
        "parent_path": list(candidate.parent_path),
        "confidence_score": candidate.confidence_score,
        "match_reasons": list(candidate.match_reasons),
        "current_context": candidate.current_context,
        "match_roles": list(candidate.match_roles),
    }


def deserialize_candidate(payload: dict[str, Any]) -> ResolvedCandidate:
    return ResolvedCandidate(
        attribute_id=str(payload.get("attribute_id") or ""),
        attribute_name=str(payload.get("attribute_name") or "").strip(),
        version_id=str(payload.get("version_id") or ""),
        data_object_id=str(payload.get("data_object_id") or ""),
        data_object_name=str(payload.get("data_object_name") or "").strip(),
        data_set_id=str(payload.get("data_set_id") or ""),
        data_set_name=str(payload.get("data_set_name") or "").strip(),
        data_product_id=str(payload.get("data_product_id") or ""),
        data_product_name=str(payload.get("data_product_name") or "").strip(),
        workspace_id=str(payload.get("workspace_id") or ""),
        parent_path=[str(item or "").strip() for item in list(payload.get("parent_path") or []) if str(item or "").strip()],
        confidence_score=float(payload.get("confidence_score") or 0),
        match_reasons=[str(item or "").strip() for item in list(payload.get("match_reasons") or []) if str(item or "").strip()],
        current_context=bool(payload.get("current_context", False)),
        match_roles=[str(item or "").strip() for item in list(payload.get("match_roles") or []) if str(item or "").strip()],
    )


def _record_in_scope(
    record: CatalogAttributeRecord,
    *,
    search_scope: str,
    current_workspace_id: str,
    allowed_workspace_ids: set[str],
) -> bool:
    if search_scope == "all_across_workspaces":
        return record.workspace_id in allowed_workspace_ids
    return record.workspace_id == current_workspace_id


def _infer_semantic_tags(
    *,
    attribute_name: str,
    parent_path: list[str],
    attribute_type: str,
    is_primary_key: bool,
    is_business_key: bool,
) -> list[str]:
    normalized_name = normalize_identifier(attribute_name)
    normalized_parent = normalize_identifier(" ".join(parent_path))
    normalized_type = normalize_identifier(attribute_type)
    tags: set[str] = set(token for token in normalized_name.split(" ") if token)

    if is_primary_key or is_business_key or normalized_name.endswith(" id") or " identifier" in normalized_name:
        tags.add("identifier")
    if any(token in normalized_name for token in ("email", "phone", "iban", "postal", "zip", "postcode", "ssn")):
        tags.add("format")
    if any(token in normalized_name for token in ("status", "country", "code", "type", "category")):
        tags.add("allowlist")
    if any(token in normalized_name for token in ("updated", "created", "modified", "timestamp", "date", "time")) or any(token in normalized_type for token in ("date", "time", "timestamp")):
        tags.add("freshness")
    if any(token in normalized_name for token in ("age", "amount", "score", "count", "pct", "percent", "rate")) or any(token in normalized_type for token in ("int", "number", "decimal", "float", "double")):
        tags.add("range")
    if "customer" in normalized_parent:
        tags.add("customer")

    return sorted(tags)


def _coerce_number(raw_value: str) -> int | float:
    value = float(raw_value)
    return int(value) if value.is_integer() else value


def _strip_wrapping_quotes(value: str) -> str:
    trimmed = str(value or "").strip()
    if (trimmed.startswith("\"") and trimmed.endswith("\"")) or (trimmed.startswith("'") and trimmed.endswith("'")) or (trimmed.startswith("`") and trimmed.endswith("`")):
        return trimmed[1:-1].strip()
    return trimmed


def _normalize_extracted_term(value: str) -> str:
    normalized = re.sub(r"^(?:a|an|the)\s+", "", str(value or "").strip(), flags=re.IGNORECASE)
    normalized = re.sub(r"^valid\s+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+address$", "", normalized, flags=re.IGNORECASE)
    return normalized.strip()


def _prompt_requires_present(prompt: str) -> bool:
    normalized = normalize_identifier(prompt)
    return bool(re.search(r"\b(filled|present|required|populated|not null)\b", normalized))


def _infer_implicit_regex_pattern(prompt: str, target_term: str) -> str | None:
    normalized_prompt = normalize_identifier(prompt)
    normalized_target = normalize_identifier(target_term)
    for token, pattern in _IMPLICIT_REGEX_PATTERNS.items():
        normalized_token = normalize_identifier(token)
        if normalized_token and (normalized_token in normalized_prompt or normalized_token in normalized_target):
            return pattern
    return None


def _candidate_matches_term(candidate: ResolvedCandidate, term: str) -> bool:
    normalized_term = normalize_identifier(term)
    normalized_name = normalize_identifier(candidate.attribute_name)
    if not normalized_term or not normalized_name:
        return False
    if normalized_name == normalized_term or normalized_name in normalized_term or normalized_term in normalized_name:
        return True

    term_tokens = {token for token in normalized_term.split("_") if token}
    name_tokens = {token for token in normalized_name.split("_") if token}
    if term_tokens and term_tokens.issubset(name_tokens):
        return True

    semantic_tokens = {
        token
        for token in ("identifier", "format", "allowlist", "freshness", "range", "customer")
        if token in normalized_term
    }
    return bool(semantic_tokens.intersection(name_tokens))


def _require_single_attribute(attribute_names: list[str], *, check_type: str) -> None:
    if len(attribute_names) != 1:
        raise ValueError(f"{check_type} draft creation requires exactly one selected attribute.")


def _dedupe_attribute_names(selected_candidates: list[ResolvedCandidate]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for candidate in selected_candidates:
        normalized = str(candidate.attribute_name or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result