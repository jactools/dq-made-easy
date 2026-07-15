"""Actuality-date tolerance resolution for cross-object DQ rules.

Provides three resolution strategies:
- DELIVERY_CONTRACT  — external catalog contract SLA lookup
- DELIVERY_METADATA  — delivery note metadata
- EXPLICIT           — author-supplied values (no lookup)

Also provides an auto-resolve helper that picks canonical actuality-date
attributes from delivery metadata or catalog heuristics.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from app.domain.entities.actuality_date_contract import ActualityDateContract
from app.domain.entities import rule_policy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ActualityDateResolutionError(RuntimeError):
    """Raised when tolerance resolution cannot be completed."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ActualityDateResolver(Protocol):
    """Resolve actuality-date tolerance for a cross-object rule."""

    async def resolve(
        self,
        *,
        actuality_contract: dict[str, Any],
        left_version_id: str,
        right_version_id: str,
        dataset_id: str | None = None,
        catalog_repository: Any | None = None,
    ) -> dict[str, Any]:
        """Return a dict with ``resolvedToleranceValue`` and ``resolvedToleranceUnit``."""
        ...


# ---------------------------------------------------------------------------
# Concrete Resolvers
# ---------------------------------------------------------------------------


class DeliveryContractActualityResolver:
    """Resolve tolerance from an external delivery contract (OpenMetadata)."""

    def __init__(self, contract_resolver: Any) -> None:
        self._contract_resolver = contract_resolver

    async def resolve(
        self,
        *,
        actuality_contract: dict[str, Any],
        left_version_id: str,
        right_version_id: str,
        dataset_id: str | None = None,
        catalog_repository: Any | None = None,
    ) -> dict[str, Any]:
        contract_id = str(actuality_contract.get("contractId") or "").strip()
        if not contract_id:
            raise ActualityDateResolutionError(
                "DELIVERY_CONTRACT toleranceSource requires 'contractId'"
            )
        try:
            policy = await self._contract_resolver.resolve_contract_policy(
                contract_id,
                dataset_id=dataset_id,
                cache_ttl_seconds=None,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", 503)
            raise ActualityDateResolutionError(
                f"Contract resolution failed for '{contract_id}': {exc}",
                status_code=status,
            ) from exc

        override_value = actuality_contract.get("overrideToleranceValue")
        override_unit = actuality_contract.get("overrideToleranceUnit")
        override_requested = override_value is not None and override_unit is not None

        if override_requested and not policy.get("overrideAllowed", False):
            raise ActualityDateResolutionError(
                f"Contract '{contract_id}' does not allow tolerance overrides",
                status_code=400,
            )

        if override_requested:
            max_ov = policy.get("maxOverrideToleranceValue")
            max_ou = policy.get("maxOverrideToleranceUnit")
            if max_ov is not None and max_ou is not None:
                if (
                    str(override_unit).lower() != str(max_ou).lower()
                    or int(override_value) > int(max_ov)
                ):
                    raise ActualityDateResolutionError(
                        f"Override exceeds contract bound of {max_ov} {max_ou}",
                        status_code=400,
                    )
            return {
                "resolvedToleranceValue": int(override_value),
                "resolvedToleranceUnit": str(override_unit).lower(),
                "contractVersion": policy.get("contractVersion"),
            }

        return {
            "resolvedToleranceValue": int(policy["resolvedToleranceValue"]),
            "resolvedToleranceUnit": str(policy["resolvedToleranceUnit"]).lower(),
            "contractVersion": policy.get("contractVersion"),
        }


class DeliveryMetadataActualityResolver:
    """Resolve actuality tolerance from delivery note metadata.

    Reads ``actuality_date`` from delivery notes and uses a configurable
    platform default tolerance.
    """

    def __init__(
        self,
        default_tolerance_value: int = 60,
        default_tolerance_unit: str = "minutes",
    ) -> None:
        self._default_tolerance_value = default_tolerance_value
        self._default_tolerance_unit = default_tolerance_unit

    async def resolve(
        self,
        *,
        actuality_contract: dict[str, Any],
        left_version_id: str,
        right_version_id: str,
        dataset_id: str | None = None,
        catalog_repository: Any | None = None,
    ) -> dict[str, Any]:
        # Delivery metadata resolution returns the platform default tolerance.
        # The actuality-date attributes are resolved separately via autoResolve.
        return {
            "resolvedToleranceValue": self._default_tolerance_value,
            "resolvedToleranceUnit": self._default_tolerance_unit,
        }


class ExplicitToleranceResolver:
    """Use author-supplied tolerance values (no external lookup)."""

    async def resolve(
        self,
        *,
        actuality_contract: dict[str, Any],
        left_version_id: str,
        right_version_id: str,
        dataset_id: str | None = None,
        catalog_repository: Any | None = None,
    ) -> dict[str, Any]:
        value = actuality_contract.get("resolvedToleranceValue")
        unit = actuality_contract.get("resolvedToleranceUnit")
        if value is None or unit is None:
            raise ActualityDateResolutionError(
                "EXPLICIT toleranceSource requires 'resolvedToleranceValue' "
                "and 'resolvedToleranceUnit' to be set directly"
            )
        return {
            "resolvedToleranceValue": int(value),
            "resolvedToleranceUnit": str(unit).lower(),
        }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class ActualityDateResolutionDispatcher:
    """Dispatch to the correct resolver based on toleranceSource."""

    def __init__(
        self,
        *,
        contract_resolver: Any | None = None,
        default_tolerance_value: int = 60,
        default_tolerance_unit: str = "minutes",
    ) -> None:
        self._contract_resolver = contract_resolver
        self._delivery_contract_resolver: DeliveryContractActualityResolver | None = (
            DeliveryContractActualityResolver(contract_resolver)
            if contract_resolver is not None
            else None
        )
        self._delivery_metadata_resolver = DeliveryMetadataActualityResolver(
            default_tolerance_value=default_tolerance_value,
            default_tolerance_unit=default_tolerance_unit,
        )
        self._explicit_resolver = ExplicitToleranceResolver()

    async def resolve(
        self,
        *,
        actuality_contract: dict[str, Any],
        left_version_id: str,
        right_version_id: str,
        dataset_id: str | None = None,
        catalog_repository: Any | None = None,
    ) -> dict[str, Any]:
        source = str(
            actuality_contract.get("toleranceSource", "DELIVERY_CONTRACT")
        ).upper()

        if source == "DELIVERY_CONTRACT":
            if self._delivery_contract_resolver is None:
                raise ActualityDateResolutionError(
                    "DELIVERY_CONTRACT resolution requires a configured contract resolver",
                    status_code=503,
                )
            return await self._delivery_contract_resolver.resolve(
                actuality_contract=dict(actuality_contract),
                left_version_id=left_version_id,
                right_version_id=right_version_id,
                dataset_id=dataset_id,
                catalog_repository=catalog_repository,
            )

        if source == "DELIVERY_METADATA":
            return await self._delivery_metadata_resolver.resolve(
                actuality_contract=dict(actuality_contract),
                left_version_id=left_version_id,
                right_version_id=right_version_id,
                dataset_id=dataset_id,
                catalog_repository=catalog_repository,
            )

        if source == "EXPLICIT":
            return await self._explicit_resolver.resolve(
                actuality_contract=dict(actuality_contract),
                left_version_id=left_version_id,
                right_version_id=right_version_id,
                dataset_id=dataset_id,
                catalog_repository=catalog_repository,
            )

        raise ActualityDateResolutionError(f"Unknown toleranceSource: {source}")


# ---------------------------------------------------------------------------
# Auto-Resolve
# ---------------------------------------------------------------------------

_ACTUALITY_HEURISTIC_KEYWORDS = (
    "actuality",
    "effective",
    "extract",
    "snapshot",
    "updated",
    "modified",
    "as_at",
    "asof",
)


def auto_resolve_actuality_attributes(
    left_version_id: str,
    right_version_id: str,
    *,
    catalog_repository: Any,
    delivery_repository: Any | None = None,
) -> tuple[str, str]:
    """Auto-pick the actuality-date attribute from each side.

    Resolution strategy (priority order):
    1. Delivery note ``actuality_date_attribute`` if set
    2. First attribute with "actuality" in the name
    3. First temporal attribute whose name contains a heuristic keyword
    4. First temporal attribute on the object
    5. Raise error if no candidate found
    """
    left_attrs = _load_attributes(catalog_repository, left_version_id)
    right_attrs = _load_attributes(catalog_repository, right_version_id)

    left_name = _pick_actuality_attribute(
        left_attrs,
        delivery_repo=delivery_repository,
        version_id=left_version_id,
        side="left",
    )
    right_name = _pick_actuality_attribute(
        right_attrs,
        delivery_repo=delivery_repository,
        version_id=right_version_id,
        side="right",
    )
    return left_name, right_name


def _load_attributes(
    catalog_repository: Any,
    version_id: str,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    try:
        for item in catalog_repository.list_attributes_catalog(version_id):
            name = str(getattr(item, "name", "") or "").strip()
            if name:
                attrs[name] = item
    except Exception as exc:
        logger.warning(
            "auto_resolve: failed to load attributes for '%s': %s",
            version_id,
            exc,
        )
    return attrs


def _pick_actuality_attribute(
    attrs: dict[str, Any],
    *,
    delivery_repo: Any | None,
    version_id: str,
    side: str,
) -> str:
    # Priority 1: delivery note actuality_date_attribute
    if delivery_repo is not None:
        try:
            delivery = delivery_repo.get_latest_delivery(version_id)
            attr_hint = getattr(delivery, "actuality_date_attribute", None)
            if attr_hint and str(attr_hint).strip() in attrs:
                return str(attr_hint).strip()
        except Exception as exc:
            logger.warning("auto_resolve: delivery lookup failed: %s", exc)

    # Priority 2: "actuality" in name
    for name in sorted(attrs.keys()):
        if "actuality" in name.lower():
            return name

    # Priority 3: temporal attribute with heuristic keyword
    for name in sorted(attrs.keys()):
        attr = attrs[name]
        attr_type = getattr(attr, "type", "") or ""
        if not rule_policy.is_temporal_attribute_type(attr_type):
            continue
        name_lower = name.lower()
        if any(kw in name_lower for kw in _ACTUALITY_HEURISTIC_KEYWORDS):
            return name

    # Priority 4: first temporal attribute
    for name in sorted(attrs.keys()):
        attr = attrs[name]
        if rule_policy.is_temporal_attribute_type(getattr(attr, "type", "")):
            return name

    raise ActualityDateResolutionError(
        f"Could not auto-resolve actuality attribute for {side} side "
        f"(version '{version_id}'). No temporal attribute found.",
        status_code=400,
    )
